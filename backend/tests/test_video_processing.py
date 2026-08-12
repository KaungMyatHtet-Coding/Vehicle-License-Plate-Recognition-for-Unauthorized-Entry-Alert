"""Deterministic tests for the disabled-by-default experimental video path."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import os
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from typing import Generator
from uuid import uuid4

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

import app.services.video_processing as video_module
from app.core.config import Settings
from app.main import app
from app.schemas.detection import (
    BoundingBox,
    ImageDetectionResponse,
    PlateCropResponse,
    PlateDetectionResponse,
)
from app.schemas.decision import EntryDecision
from app.schemas.ocr import PlateOcrResponse
from app.services.recognition_orchestration import RecognitionAnalysis
from app.services.video_processing import (
    MAX_VIDEO_SIZE_BYTES,
    VideoProcessingService,
    VideoValidationError,
)

client = TestClient(app)


def isolated_settings(**values: object) -> Settings:
    return Settings(_env_file=None, **values)


def generate_test_video_bytes(duration_sec: float = 2.0, fps: int = 10) -> bytes:
    """Generate a small local MP4 fixture and remove its source file."""

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp_path = tmp.name
    tmp.close()
    try:
        out = cv2.VideoWriter(
            tmp_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (320, 240)
        )
        for index in range(int(duration_sec * fps)):
            frame = np.full((240, 320, 3), 100, dtype=np.uint8)
            cv2.putText(
                frame,
                f"F{index}",
                (50, 120),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (255, 255, 255),
                2,
            )
            out.write(frame)
        out.release()
        return open(tmp_path, "rb").read()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def make_analysis(
    correlation_id: str,
    normalized_text: str | None = "YGN1234",
    confidence: float = 0.95,
) -> RecognitionAnalysis:
    candidate = PlateDetectionResponse(
        bbox=BoundingBox(x1=80, y1=140, x2=240, y2=190),
        confidence=0.98,
        label="license_plate",
        crop=PlateCropResponse(
            media_type="image/png",
            width=160,
            height=50,
            base64_data="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        ),
    )
    detection = ImageDetectionResponse(
        correlation_id=correlation_id,
        status="completed" if normalized_text else "no_plate_detected",
        detection_count=1 if normalized_text else 0,
        image_width=320,
        image_height=240,
        inference_ms=10.0,
        total_ms=10.0,
        detections=[candidate] if normalized_text else [],
    )
    if normalized_text is None:
        return RecognitionAnalysis(detection, None, None, None, 10.0, 5.0)
    ocr = PlateOcrResponse(
        correlation_id=correlation_id,
        status="recognized",
        review_reason=None,
        raw_text=normalized_text,
        normalized_text=normalized_text,
        confidence=confidence,
        mode="full_pipeline",
        inference_ms=5.0,
        total_ms=5.0,
        image_width=160,
        image_height=50,
    )
    decision = EntryDecision(
        correlation_id=correlation_id,
        decision="AUTHORIZED",
        reason="ACTIVE_MATCH",
        message="Authorized vehicle.",
        normalized_plate=normalized_text,
        confidence=confidence,
        vehicle_id=None,
        evaluated_at=datetime.now(timezone.utc),
    )
    return RecognitionAnalysis(detection, candidate, ocr, decision, 10.0, 5.0)


class FakeOrchestration:
    def __init__(
        self,
        analyses: list[RecognitionAnalysis],
        *,
        persist_success: bool = True,
        persist_exception: Exception | None = None,
    ) -> None:
        self._analyses = deque(analyses)
        self.persisted: list[tuple[bytes, RecognitionAnalysis, str]] = []
        self.analyzed_frames: list[tuple[bytes, RecognitionAnalysis]] = []
        self.analyze_calls = 0
        self.persist_success = persist_success
        self.persist_exception = persist_exception

    def analyze(self, image_bytes: bytes, correlation_id: str) -> RecognitionAnalysis:
        self.analyze_calls += 1
        if len(self._analyses) > 1:
            analysis = self._analyses.popleft()
        else:
            analysis = self._analyses[0]
        self.analyzed_frames.append((image_bytes, analysis))
        return analysis

    def _persist_analysis(
        self,
        image_bytes: bytes,
        analysis: RecognitionAnalysis,
        correlation_id: str,
        *,
        validate_identity: bool,
    ) -> SimpleNamespace:
        self.persisted.append((image_bytes, analysis, correlation_id))
        if self.persist_exception is not None:
            raise self.persist_exception
        logging = SimpleNamespace(
            log_persisted=self.persist_success,
            decision=SimpleNamespace(decision="AUTHORIZED", reason="ACTIVE_MATCH"),
        )
        return SimpleNamespace(logging=logging)


@pytest.fixture(autouse=True)
def clear_overrides() -> Generator[None, None, None]:
    yield
    app.dependency_overrides.clear()


def test_video_validation_is_fail_closed() -> None:
    service = VideoProcessingService(
        FakeOrchestration([make_analysis(str(uuid4()))]),
        settings=isolated_settings(),
    )
    cases = [
        (b"", "video.mp4", "VIDEO_EMPTY"),
        (b"x" * (MAX_VIDEO_SIZE_BYTES + 1), "video.mp4", "VIDEO_OVERSIZED"),
        (b"fake", "video.txt", "VIDEO_FORMAT_UNSUPPORTED"),
        (b"fake", "", "VIDEO_FILENAME_REQUIRED"),
        (b"fake", "video.mp4", "VIDEO_CORRUPT"),
    ]
    for content, filename, code in cases:
        with pytest.raises(VideoValidationError) as raised:
            service.process_video(content, filename, str(uuid4()))
        assert raised.value.code == code


def test_video_repeated_exact_observations_persist_once_without_frame_leak() -> None:
    correlation_id = str(uuid4())
    best = make_analysis(correlation_id, confidence=0.99)
    lower = make_analysis(correlation_id, confidence=0.90)
    orchestration = FakeOrchestration([best, lower])
    service = VideoProcessingService(
        orchestration,
        settings=isolated_settings(VIDEO_CONSENSUS_MIN_OBSERVATIONS=2),
    )
    result = service.process_video(
        generate_test_video_bytes(), "sample.mp4", correlation_id
    )
    assert result.unique_plates_count == 1
    assert len(orchestration.persisted) == 1
    assert orchestration.persisted[0][0].startswith(b"\xff\xd8")
    assert orchestration.analyze_calls == result.total_frames_analyzed
    assert orchestration.persisted[0][1] is best
    assert orchestration.persisted[0][0] == orchestration.analyzed_frames[0][0]
    assert orchestration.persisted[0][1].selected is best.selected
    assert "YGN1234" not in result.model_dump_json() or result.unique_plates_count == 1


def test_video_insufficient_or_conflicting_consensus_does_not_persist() -> None:
    correlation_id = str(uuid4())
    orchestration = FakeOrchestration(
        [
            make_analysis(correlation_id, "YGN1234"),
            make_analysis(correlation_id, "MDY5678"),
        ]
    )
    service = VideoProcessingService(
        orchestration,
        settings=isolated_settings(VIDEO_CONSENSUS_MIN_OBSERVATIONS=2),
    )
    result = service.process_video(
        generate_test_video_bytes(), "sample.mp4", correlation_id
    )
    assert len(orchestration.persisted) == 0
    assert result.detections[0].decision == "MANUAL_REVIEW"
    assert "YGN1234" not in result.model_dump_json()
    assert "MDY5678" not in result.model_dump_json()


def test_video_no_plate_has_no_persistence() -> None:
    correlation_id = str(uuid4())
    orchestration = FakeOrchestration(
        [make_analysis(correlation_id, None), make_analysis(correlation_id, None)]
    )
    result = VideoProcessingService(
        orchestration, settings=isolated_settings()
    ).process_video(generate_test_video_bytes(), "sample.mp4", correlation_id)
    assert result.detections[0].status == "no_plate_detected"
    assert orchestration.persisted == []


def test_video_persistence_failure_is_sanitized() -> None:
    correlation_id = str(uuid4())
    orchestration = FakeOrchestration(
        [make_analysis(correlation_id), make_analysis(correlation_id)],
        persist_exception=RuntimeError("provider path and secret"),
    )
    with pytest.raises(VideoValidationError) as raised:
        VideoProcessingService(
            orchestration, settings=isolated_settings()
        ).process_video(generate_test_video_bytes(), "sample.mp4", correlation_id)
    assert raised.value.code == "VIDEO_PERSISTENCE_FAILED"
    assert "provider" not in str(raised.value)
    assert "secret" not in str(raised.value)


def test_unsuccessful_logging_result_is_not_reported_as_persisted() -> None:
    correlation_id = str(uuid4())
    orchestration = FakeOrchestration(
        [make_analysis(correlation_id), make_analysis(correlation_id)],
        persist_success=False,
    )
    with pytest.raises(VideoValidationError) as raised:
        VideoProcessingService(
            orchestration, settings=isolated_settings()
        ).process_video(generate_test_video_bytes(), "sample.mp4", correlation_id)
    assert raised.value.code == "VIDEO_PERSISTENCE_FAILED"
    assert len(orchestration.persisted) == 1


def test_video_temporary_file_is_removed_on_decoder_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    removed: list[str] = []
    original_remove = video_module.os.remove

    def record_remove(path: str) -> None:
        removed.append(path)
        original_remove(path)

    monkeypatch.setattr(video_module.os, "remove", record_remove)
    with pytest.raises(VideoValidationError, match="could not be decoded"):
        VideoProcessingService(
            FakeOrchestration([make_analysis(str(uuid4()))]),
            settings=isolated_settings(),
        ).process_video(b"not-a-real-video", "sample.mp4", str(uuid4()))
    assert removed
    assert all(not os.path.exists(path) for path in removed)


def test_video_configuration_rejects_inconsistent_bounds() -> None:
    with pytest.raises(ValueError, match="CONSENSUS_MIN"):
        isolated_settings(
            VIDEO_CONSENSUS_MIN_OBSERVATIONS=4,
            VIDEO_CONSENSUS_WINDOW_FRAMES=2,
        )
    with pytest.raises(ValueError, match="SAMPLED_FRAMES"):
        isolated_settings(
            VIDEO_MAX_SAMPLED_FRAMES=301,
            VIDEO_MAX_DECODED_FRAMES=300,
        )
    with pytest.raises(ValueError, match="WINDOW_FRAMES"):
        isolated_settings(
            VIDEO_CONSENSUS_WINDOW_FRAMES=3,
            VIDEO_MAX_SAMPLED_FRAMES=2,
        )
    with pytest.raises(ValueError, match="invalid extension"):
        isolated_settings(VIDEO_ALLOWED_EXTENSIONS=".mp4,.mkv")


def test_video_frame_and_decode_limits_fail_closed() -> None:
    correlation_id = str(uuid4())
    orchestration = FakeOrchestration([make_analysis(correlation_id)])
    with pytest.raises(VideoValidationError, match="dimensions"):
        VideoProcessingService(
            orchestration,
            settings=isolated_settings(VIDEO_MAX_FRAME_WIDTH=100),
        ).process_video(generate_test_video_bytes(0.5), "sample.mp4", correlation_id)

    with pytest.raises(VideoValidationError, match="decoded-frame"):
        VideoProcessingService(
            orchestration,
            settings=isolated_settings(
                VIDEO_MAX_DECODED_FRAMES=2,
                VIDEO_MAX_SAMPLED_FRAMES=2,
                VIDEO_CONSENSUS_WINDOW_FRAMES=2,
            ),
        ).process_video(generate_test_video_bytes(0.5), "sample.mp4", correlation_id)


def test_api_analyze_video_endpoint_is_disabled_by_default() -> None:
    assert "/api/recognition/analyze-video" not in app.openapi()["paths"]
    assert client.post("/api/recognition/analyze-video").status_code == 404


def test_api_analyze_video_opt_in_registers_route_in_fresh_process() -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "CVPX_DISABLE_DOTENV": "1",
            "APP_MODE": "localhost",
            "REPOSITORY_MODE": "memory",
            "ENABLE_EXPERIMENTAL_VIDEO": "true",
            "APP_HOST": "127.0.0.1",
            "FRONTEND_ORIGINS": "http://localhost:3000",
        }
    )
    environment.pop("SUPABASE_URL", None)
    environment.pop("SUPABASE_SERVICE_ROLE_KEY", None)
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "from fastapi.testclient import TestClient; from app.main import app; "
            "p='/api/recognition/analyze-video'; r=TestClient(app).post(p); "
            "print(sum(1 for path in app.openapi()['paths'] if path == p)); "
            "print(r.status_code, r.json()['error']['code'])",
        ],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert probe.stdout.splitlines() == ["1", "422 VALIDATION_ERROR"]


def test_default_import_does_not_open_video_decoder() -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "CVPX_DISABLE_DOTENV": "1",
            "APP_MODE": "localhost",
            "REPOSITORY_MODE": "memory",
            "ENABLE_EXPERIMENTAL_VIDEO": "false",
            "APP_HOST": "127.0.0.1",
            "FRONTEND_ORIGINS": "http://localhost:3000",
        }
    )
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import cv2; cv2.VideoCapture=lambda *a, **k: (_ for _ in ()).throw(AssertionError('decoder opened')); "
            "from app.main import app; print('/api/recognition/analyze-video' in app.openapi()['paths'])",
        ],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert probe.stdout.strip() == "False"
