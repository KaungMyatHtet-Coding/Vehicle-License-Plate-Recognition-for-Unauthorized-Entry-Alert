"""Camera-free tests for the bounded local webcam state and runner."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import numpy as np
import pytest

_SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
for _path in (_SCRIPTS, _BACKEND):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from run_webcam import CameraUnavailableError, WebcamRunner, parse_args  # noqa: E402
from webcam_consensus import (  # noqa: E402
    CooldownLedger,
    TemporalConsensus,
    TrackObservation,
    clip_bbox,
)


def _observation(
    text: str | None,
    bbox: tuple[int, int, int, int] = (10, 10, 50, 30),
    timestamp: float = 1.0,
    reliable: bool = True,
) -> TrackObservation:
    return TrackObservation(
        bbox, text, reliable, 0.9 if reliable else 0.0, timestamp, object()
    )


def test_parse_args_defaults_and_bounds() -> None:
    args = parse_args([])
    assert (args.camera, args.fps, args.cooldown) == (0, 2.0, 3.0)
    assert (args.consensus_window, args.agreement_count, args.max_tracks) == (4, 2, 8)
    with pytest.raises(SystemExit):
        parse_args(["--fps", "0"])


def test_clip_bbox_uses_real_coordinates_and_rejects_zero_area() -> None:
    assert clip_bbox((-4, 3, 110, 40), 100, 50) == (0, 3, 100, 40)
    assert clip_bbox((2, 2, 2, 8), 100, 50) is None
    assert clip_bbox((2, 2, 8, 2), 100, 50) is None


def test_exact_repeated_observations_reach_consensus() -> None:
    consensus = TemporalConsensus(required_agreements=2, observation_window=3)
    assert (
        consensus.update(_observation("YGN12345", timestamp=1)).status
        == "MANUAL_REVIEW"
    )
    result = consensus.update(_observation("YGN12345", timestamp=2))
    assert result.status == "stable"
    assert result.normalized_text == "YGN12345"


def test_single_observation_and_disagreement_stay_unresolved() -> None:
    consensus = TemporalConsensus(required_agreements=2, observation_window=4)
    assert (
        consensus.update(_observation("YGN12345", timestamp=1)).status
        == "MANUAL_REVIEW"
    )
    assert (
        consensus.update(_observation("MDY12345", timestamp=2)).status
        == "MANUAL_REVIEW"
    )
    assert (
        consensus.update(_observation("YGN1234S", timestamp=3)).status
        == "MANUAL_REVIEW"
    )


def test_spatially_separate_vehicles_do_not_merge() -> None:
    consensus = TemporalConsensus(required_agreements=2, observation_window=3)
    consensus.update(_observation("YGN12345", (0, 0, 20, 10), 1))
    consensus.update(_observation("MDY12345", (80, 0, 100, 10), 2))
    assert consensus.track_count == 2


def test_character_disagreement_and_distinct_reliable_text_never_stabilize() -> None:
    consensus = TemporalConsensus(required_agreements=2, observation_window=4)
    consensus.update(_observation("YGN5D3062", timestamp=1))
    consensus.update(_observation("YGN5D3062", timestamp=2))
    result = consensus.update(_observation("YGN503062", timestamp=3))
    assert result.status == "MANUAL_REVIEW"
    assert result.normalized_text is None
    assert not hasattr(result, "alternatives")


def test_track_expiry_and_bounded_track_count() -> None:
    consensus = TemporalConsensus(
        required_agreements=2,
        observation_window=2,
        track_expiry_seconds=1,
        max_tracks=2,
    )
    consensus.update(_observation("YGN12345", (0, 0, 10, 10), 1))
    consensus.update(_observation("MDY12345", (20, 0, 30, 10), 1.1))
    consensus.update(_observation("NPT12345", (40, 0, 50, 10), 1.2))
    assert consensus.track_count == 2
    consensus.update(_observation("YGN12345", (0, 0, 10, 10), 3))
    assert consensus.track_count == 1


def test_observation_window_and_cooldown_are_bounded_and_expire() -> None:
    consensus = TemporalConsensus(required_agreements=2, observation_window=2)
    consensus.update(_observation("YGN12345", timestamp=1))
    consensus.update(_observation("YGN12345", timestamp=2))
    assert len(consensus._tracks[1].observations) == 2
    ledger = CooldownLedger(3, max_entries=2)
    assert ledger.is_suppressed("YGN12345", 1) is False
    ledger.record("YGN12345", 1)
    assert ledger.is_suppressed("YGN12345", 2) is True
    assert ledger.is_suppressed("MDY12345", 2) is False
    ledger.record("MDY12345", 2)
    assert ledger.is_suppressed("NPT12345", 2) is False
    ledger.record("NPT12345", 2)
    assert ledger.size == 2
    assert ledger.is_suppressed("YGN12345", 5) is False


def test_consensus_persists_selected_observation_frame_and_identity() -> None:
    old_correlation = str(uuid4())
    new_correlation = str(uuid4())
    old_analysis = SimpleNamespace(name="old")
    new_analysis = SimpleNamespace(name="new")
    consensus = TemporalConsensus(required_agreements=2, observation_window=3)
    old = TrackObservation(
        (10, 10, 50, 30),
        "YGN12345",
        True,
        0.99,
        1.0,
        old_analysis,
        b"old-frame",
        old_correlation,
    )
    new = TrackObservation(
        (10, 10, 50, 30),
        "YGN12345",
        True,
        0.80,
        2.0,
        new_analysis,
        b"new-frame",
        new_correlation,
    )
    consensus.update(old)
    result = consensus.update(new)
    assert result.observation is old

    calls: list[tuple[bytes, object, str]] = []

    class Service:
        def _persist_analysis(self, frame: bytes, analysis: object, correlation: str):
            calls.append((frame, analysis, correlation))
            return SimpleNamespace(logging=SimpleNamespace(log_persisted=True))

    runner = WebcamRunner(service=Service())  # type: ignore[arg-type]
    response, suppressed, persisted = runner._persist_consensus_observation(
        result.observation,
        2.0,  # type: ignore[arg-type]
    )
    assert response is not None
    assert suppressed is False
    assert persisted is True
    assert calls == [(b"old-frame", old_analysis, old_correlation)]


def test_observation_frame_bytes_are_bounded_and_released_on_expiry_and_eviction() -> (
    None
):
    consensus = TemporalConsensus(
        required_agreements=2,
        observation_window=2,
        track_expiry_seconds=1,
        max_tracks=1,
    )
    first = TrackObservation(
        (0, 0, 10, 10), "YGN12345", True, 0.9, 1, object(), b"first", "first"
    )
    second = TrackObservation(
        (0, 0, 10, 10), "YGN12345", True, 0.9, 1.1, object(), b"second", "second"
    )
    third = TrackObservation(
        (30, 0, 40, 10), "MDY12345", True, 0.9, 1.2, object(), b"third", "third"
    )
    consensus.update(first)
    consensus.update(second)
    old_track = consensus._tracks[1]
    consensus.update(third)
    assert len(old_track.observations) == 0
    assert all(
        observation.frame_bytes != b"first"
        for track in consensus._tracks.values()
        for observation in track.observations
    )
    expired_track = consensus._tracks[2]
    consensus.update(
        TrackObservation(
            (30, 0, 40, 10),
            "MDY12345",
            True,
            0.9,
            3,
            object(),
            b"expired",
            "expired",
        )
    )
    assert len(consensus._tracks) == 1
    assert len(expired_track.observations) == 0


def test_successful_persistence_records_cooldown_and_active_cooldown_skips_call() -> (
    None
):
    calls = 0

    class Service:
        def _persist_analysis(self, *_args: object) -> object:
            nonlocal calls
            calls += 1
            return SimpleNamespace(logging=SimpleNamespace(log_persisted=True))

    observation = _observation("YGN12345")
    runner = WebcamRunner(service=Service())  # type: ignore[arg-type]
    response, suppressed, persisted = runner._persist_consensus_observation(
        observation, 1
    )
    assert response is not None and suppressed is False and persisted is True
    response, suppressed, persisted = runner._persist_consensus_observation(
        observation, 2
    )
    assert response is None and suppressed is True and persisted is False
    assert calls == 1


@pytest.mark.parametrize("failure", ["raise", "false"])
def test_failed_persistence_does_not_record_cooldown_and_can_retry(
    failure: str,
) -> None:
    calls = 0

    class Service:
        def _persist_analysis(self, *_args: object) -> object:
            nonlocal calls
            calls += 1
            if calls == 1 and failure == "raise":
                raise RuntimeError("provider failure")
            return SimpleNamespace(
                logging=SimpleNamespace(log_persisted=failure != "false" or calls > 1)
            )

    observation = _observation("YGN12345")
    runner = WebcamRunner(service=Service())  # type: ignore[arg-type]
    response, suppressed, persisted = runner._persist_consensus_observation(
        observation, 1
    )
    assert response is None or persisted is False
    assert suppressed is False and persisted is False
    assert runner._cooldown.size == 0
    response, suppressed, persisted = runner._persist_consensus_observation(
        observation, 2
    )
    assert suppressed is False and persisted is True
    assert response is not None
    assert calls == 2


def test_unresolved_observation_never_persists() -> None:
    calls = 0

    class Service:
        def _persist_analysis(self, *_args: object) -> object:
            nonlocal calls
            calls += 1
            return SimpleNamespace(logging=SimpleNamespace(log_persisted=True))

    runner = WebcamRunner(service=Service())  # type: ignore[arg-type]
    unresolved = _observation("YGN12345", reliable=False)
    response, suppressed, persisted = runner._persist_consensus_observation(
        unresolved, 1
    )
    assert response is None and suppressed is False and persisted is False
    assert calls == 0


def test_overlay_draws_actual_bbox_and_safe_status() -> None:
    runner = WebcamRunner()
    frame = np.zeros((60, 80, 3), dtype=np.uint8)
    with (
        patch("run_webcam.cv2.putText"),
        patch("run_webcam.cv2.rectangle") as rectangle,
    ):
        runner._draw_overlay(
            frame, "YGN12345", "AUTHORIZED", False, (3, 4, 20, 25), 1, 2
        )
    rectangle.assert_any_call(frame, (3, 4), (20, 25), (0, 255, 0), 2)


class _ClosedCapture:
    def isOpened(self) -> bool:
        return False

    def release(self) -> None:
        self.released = True


def test_camera_open_failure_is_safe() -> None:
    runner = WebcamRunner(capture_factory=lambda _index: _ClosedCapture())
    with pytest.raises(CameraUnavailableError):
        runner.open_camera()


def test_camera_read_failure_releases_camera_and_destroys_window() -> None:
    class Capture:
        def isOpened(self) -> bool:
            return True

        def read(self) -> tuple[bool, None]:
            return False, None

        def release(self) -> None:
            self.released = True

    capture = Capture()
    runner = WebcamRunner(capture_factory=lambda _index: capture)
    with patch("run_webcam.cv2.destroyAllWindows") as destroy:
        assert runner.run() == 1
    assert capture.released is True
    destroy.assert_called_once_with()


def test_q_escape_and_ctrl_c_paths_cleanup_camera() -> None:
    class Capture:
        def isOpened(self) -> bool:
            return True

        def read(self) -> tuple[bool, np.ndarray]:
            return True, np.zeros((40, 50, 3), dtype=np.uint8)

        def release(self) -> None:
            self.released = True

    for key in (ord("q"), 27):
        capture = Capture()
        runner = WebcamRunner(capture_factory=lambda _index, item=capture: item)
        with (
            patch("run_webcam.cv2.imshow"),
            patch("run_webcam.cv2.waitKey", return_value=key),
            patch("run_webcam.cv2.destroyAllWindows") as destroy,
        ):
            assert runner.run() == 0
        assert capture.released is True
        destroy.assert_called_once_with()

    capture = Capture()
    runner = WebcamRunner(capture_factory=lambda _index: capture)
    with (
        patch("run_webcam.cv2.imshow"),
        patch("run_webcam.cv2.waitKey", side_effect=KeyboardInterrupt),
        patch("run_webcam.cv2.destroyAllWindows") as destroy,
    ):
        assert runner.run() == 0
    assert capture.released is True
    destroy.assert_called_once_with()


def test_inference_failure_stays_unresolved_without_persistence() -> None:
    class FailingService:
        def analyze(self, _image: bytes, _correlation: str) -> object:
            raise RuntimeError("inference failure")

    runner = WebcamRunner(service=FailingService())  # type: ignore[arg-type]
    frame = np.zeros((40, 50, 3), dtype=np.uint8)
    encoded = runner._encode_frame(frame)
    assert encoded is not None
    analysis, observation = runner._analyze_frame(frame, encoded)
    assert analysis is None
    assert observation is None


def test_runner_persists_once_after_consensus_and_not_on_cooldown() -> None:
    correlation_id = str(uuid4())
    selected = SimpleNamespace(bbox=SimpleNamespace(x1=2, y1=2, x2=30, y2=15))
    ocr = SimpleNamespace(
        correlation_id=correlation_id,
        normalized_text="YGN12345",
        status="recognized",
        confidence=0.95,
    )
    analysis = SimpleNamespace(selected=selected, ocr=ocr)
    logging_result = SimpleNamespace(decision=SimpleNamespace(decision="UNAUTHORIZED"))
    response = SimpleNamespace(
        logging=SimpleNamespace(
            decision=logging_result.decision,
            log_persisted=True,
        )
    )

    class FakeService:
        def __init__(self) -> None:
            self.persisted = 0

        def analyze(self, _image: bytes, _correlation: str) -> object:
            return analysis

        def _persist_analysis(
            self, _image: bytes, _analysis: object, _correlation: str
        ) -> object:
            self.persisted += 1
            return response

    class Capture:
        def isOpened(self) -> bool:
            return True

        def read(self) -> tuple[bool, np.ndarray]:
            return True, np.zeros((40, 50, 3), dtype=np.uint8)

        def release(self) -> None:
            self.released = True

    service = FakeService()
    runner = WebcamRunner(
        target_fps=1_000_000,
        cooldown_seconds=100,
        service=service,  # type: ignore[arg-type]
        capture_factory=lambda _index: Capture(),
    )
    keys = iter([255, 255, ord("q")])
    with (
        patch("run_webcam.cv2.imshow"),
        patch("run_webcam.cv2.waitKey", side_effect=lambda _delay: next(keys)),
        patch("run_webcam.time.monotonic", side_effect=[1.0, 1.1, 2.0, 2.1, 3.0, 3.1]),
    ):
        assert runner.run() == 0
    assert service.persisted == 1
    assert runner._cooldown.size == 1


def test_backend_import_and_webcam_import_have_no_camera_side_effects() -> None:
    import app.main  # noqa: F401
    import run_webcam  # noqa: F401
