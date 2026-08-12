"""Local-only webcam demo with bounded temporal consensus.

The CLI constructs the existing Phase 4 services directly. It never sends
sampled frames through the public persistence-producing HTTP endpoint.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys
import time
from typing import Any, Callable, Sequence
from uuid import uuid4

import cv2

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.config import get_settings  # noqa: E402
from app.dependencies import get_application_dependencies  # noqa: E402
from app.services.authorization_decision import AuthorizationDecisionService  # noqa: E402
from app.services.detection_logging import DetectionLoggingService  # noqa: E402
from app.services.ocr_recognition import PlateOcrService  # noqa: E402
from app.services.plate_detection import PlateDetectionService  # noqa: E402
from app.services.recognition_orchestration import (  # noqa: E402
    RecognitionAnalysis,
    RecognitionOrchestrationService,
)
from webcam_consensus import (  # noqa: E402
    CooldownLedger,
    TemporalConsensus,
    TrackObservation,
    clip_bbox,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WebcamDemo] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class CameraUnavailableError(RuntimeError):
    """Raised when the requested camera index cannot be opened."""


class WebcamRunner:
    """Run bounded local analysis and persist only stable, unsuppressed events."""

    def __init__(
        self,
        camera_index: int = 0,
        target_fps: float = 2.0,
        cooldown_seconds: float = 3.0,
        api_base_url: str = "http://127.0.0.1:8000",
        *,
        consensus_window: int = 4,
        agreement_count: int = 2,
        track_expiry_seconds: float = 2.0,
        max_tracks: int = 8,
        iou_threshold: float = 0.30,
        service: RecognitionOrchestrationService | None = None,
        capture_factory: Callable[[int], Any] = cv2.VideoCapture,
    ) -> None:
        if target_fps <= 0 or cooldown_seconds <= 0:
            raise ValueError("fps and cooldown must be positive")
        self._camera_index = camera_index
        self._target_fps = target_fps
        self._cooldown_seconds = cooldown_seconds
        self._api_base_url = api_base_url.rstrip("/")
        self._service = service
        self._capture_factory = capture_factory
        self._consensus = TemporalConsensus(
            required_agreements=agreement_count,
            observation_window=consensus_window,
            track_expiry_seconds=track_expiry_seconds,
            max_tracks=max_tracks,
            iou_threshold=iou_threshold,
        )
        self._cooldown = CooldownLedger(cooldown_seconds)

    def _build_service(self) -> RecognitionOrchestrationService:
        if self._service is not None:
            return self._service
        settings = get_settings()
        dependencies = get_application_dependencies()
        self._service = RecognitionOrchestrationService(
            PlateDetectionService(settings),
            PlateOcrService(settings),
            AuthorizationDecisionService(dependencies.vehicles, settings),
            DetectionLoggingService(
                dependencies.detection_logs,
                dependencies.evidence_storage,
                settings,
            ),
            dependencies.recognition_activity,
            settings,
        )
        return self._service

    def open_camera(self) -> Any:
        """Open camera and raise a safe error if it cannot be accessed."""
        capture = self._capture_factory(self._camera_index)
        if not capture.isOpened():
            try:
                capture.release()
            except Exception:
                pass
            raise CameraUnavailableError(
                f"Camera index {self._camera_index} is unavailable or not connected."
            )
        return capture

    @staticmethod
    def _encode_frame(frame: Any) -> bytes | None:
        success, encoded = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85]
        )
        if not success or encoded.nbytes > 10 * 1024 * 1024:
            return None
        return encoded.tobytes()

    def _analyze_frame(
        self, frame: Any, frame_bytes: bytes
    ) -> tuple[RecognitionAnalysis | None, TrackObservation | None]:
        correlation_id = str(uuid4())
        try:
            analysis = self._build_service().analyze(frame_bytes, correlation_id)
        except Exception:
            logger.warning("Frame analysis failed; keeping the event unresolved.")
            return None, None
        selected = analysis.selected
        if selected is None:
            return analysis, None
        height, width = frame.shape[:2]
        raw_bbox = (
            selected.bbox.x1,
            selected.bbox.y1,
            selected.bbox.x2,
            selected.bbox.y2,
        )
        bbox = clip_bbox(raw_bbox, int(width), int(height))
        if bbox is None:
            return analysis, None
        ocr = analysis.ocr
        normalized = getattr(ocr, "normalized_text", None)
        confidence = getattr(ocr, "confidence", None)
        reliable = (
            getattr(ocr, "status", None) == "recognized"
            and isinstance(normalized, str)
            and bool(normalized)
            and isinstance(confidence, (float, int))
            and not isinstance(confidence, bool)
        )
        observation = TrackObservation(
            bbox=bbox,
            normalized_text=normalized if isinstance(normalized, str) else None,
            reliable=reliable,
            confidence=float(confidence) if reliable else 0.0,
            timestamp=time.monotonic(),
            analysis=analysis,
            frame_bytes=frame_bytes,
            correlation_id=correlation_id,
        )
        return analysis, observation

    def _persist_consensus_observation(
        self, observation: TrackObservation, timestamp: float
    ) -> tuple[Any | None, bool, bool]:
        """Persist one observation only after cooldown and record success."""

        text = observation.normalized_text or ""
        if not observation.reliable or not text:
            return None, False, False
        if self._cooldown.is_suppressed(text, timestamp):
            return None, True, False
        try:
            response = self._build_service()._persist_analysis(
                observation.frame_bytes,
                observation.analysis,
                observation.correlation_id,
            )
        except Exception:
            logger.warning("Stable event persistence failed; it remains retryable.")
            return None, False, False
        logging_result = getattr(response, "logging", None)
        if getattr(logging_result, "log_persisted", False) is True:
            self._cooldown.record(text, timestamp)
            return response, False, True
        logger.warning("Stable event was not persisted; it remains retryable.")
        return response, False, False

    def _draw_overlay(
        self,
        frame: Any,
        plate: str | None,
        decision: str | None,
        suppressed: bool,
        bbox: tuple[int, int, int, int] | None,
        fps: float,
        latency_ms: float,
    ) -> Any:
        """Draw only the selected, clipped box and safe workflow status."""
        height, width = frame.shape[:2]
        if bbox is not None:
            color = (0, 255, 0) if decision == "AUTHORIZED" else (0, 165, 255)
            if decision == "UNAUTHORIZED":
                color = (0, 0, 255)
            cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), color, 2)
        cv2.putText(
            frame,
            f"FPS: {fps:.1f}  Latency: {latency_ms:.0f}ms",
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2,
        )
        status = "collecting/unresolved"
        if suppressed:
            status = "suppressed duplicate"
        elif decision:
            status = decision
        elif plate:
            status = "MANUAL_REVIEW"
        cv2.rectangle(
            frame, (10, height - 55), (width - 10, height - 10), (0, 0, 0), -1
        )
        cv2.putText(
            frame,
            f"{status}{(': ' + plate) if plate else ''}",
            (15, height - 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
        )
        return frame

    def run(self) -> int:
        """Run until Q, Escape, Ctrl+C, or a safe camera/runtime failure."""
        try:
            capture = self.open_camera()
        except CameraUnavailableError as exc:
            logger.error("Camera unavailable: %s", exc)
            return 1

        frame_interval = 1.0 / self._target_fps
        last_sample = 0.0
        display: tuple[
            str | None, str | None, bool, tuple[int, int, int, int] | None
        ] = (
            None,
            None,
            False,
            None,
        )
        loop_times: list[float] = []
        latency_ms = 0.0
        try:
            while True:
                started = time.perf_counter()
                ok, frame = capture.read()
                if not ok or frame is None:
                    logger.warning("Failed to read frame from camera; stopping safely.")
                    return 1
                now = time.monotonic()
                if now - last_sample >= frame_interval:
                    last_sample = now
                    encoded = self._encode_frame(frame)
                    if encoded is not None:
                        _analysis, observation = self._analyze_frame(frame, encoded)
                        latency_ms = (time.perf_counter() - started) * 1000
                        if observation is None:
                            display = (None, None, False, None)
                        else:
                            consensus = self._consensus.update(observation)
                            if consensus.status != "stable":
                                display = (
                                    observation.normalized_text,
                                    "MANUAL_REVIEW",
                                    False,
                                    observation.bbox,
                                )
                            else:
                                assert consensus.observation is not None
                                stable = consensus.observation
                                response, suppressed, persisted = (
                                    self._persist_consensus_observation(stable, now)
                                )
                                decision = (
                                    response.logging.decision.decision
                                    if response and response.logging and persisted
                                    else None
                                )
                                display = (
                                    consensus.normalized_text,
                                    decision if persisted else "MANUAL_REVIEW",
                                    suppressed,
                                    stable.bbox,
                                )

                elapsed = time.perf_counter() - started
                loop_times.append(elapsed)
                if len(loop_times) > 30:
                    loop_times.pop(0)
                measured = (
                    1.0 / (sum(loop_times) / len(loop_times)) if loop_times else 0.0
                )
                self._draw_overlay(frame, *display, measured, latency_ms)
                cv2.imshow("CVPX - Webcam Demo (Press Q to quit)", frame)
                if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
                    return 0
        except KeyboardInterrupt:
            logger.info("Interrupted by user.")
            return 0
        finally:
            try:
                capture.release()
            finally:
                cv2.destroyAllWindows()


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _bounded_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_webcam.py",
        description="CVPX local webcam demo with non-persisting analysis and temporal consensus.",
    )
    parser.add_argument("--camera", type=int, default=0, metavar="INDEX")
    parser.add_argument("--fps", type=_positive_float, default=2.0, metavar="FPS")
    parser.add_argument(
        "--cooldown", type=_positive_float, default=3.0, metavar="SECONDS"
    )
    parser.add_argument(
        "--api-url", default="http://127.0.0.1:8000", help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--consensus-window", type=_bounded_int, default=4, metavar="FRAMES"
    )
    parser.add_argument(
        "--agreement-count", type=_bounded_int, default=2, metavar="FRAMES"
    )
    parser.add_argument(
        "--track-expiry", type=_positive_float, default=2.0, metavar="SECONDS"
    )
    parser.add_argument("--max-tracks", type=_bounded_int, default=8, metavar="COUNT")
    parser.add_argument("--iou-threshold", type=float, default=0.30, metavar="RATIO")
    args = parser.parse_args(argv)
    if args.agreement_count > args.consensus_window:
        parser.error("--agreement-count cannot exceed --consensus-window")
    if not 0.0 <= args.iou_threshold <= 1.0:
        parser.error("--iou-threshold must be between zero and one")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        runner = WebcamRunner(
            camera_index=args.camera,
            target_fps=args.fps,
            cooldown_seconds=args.cooldown,
            api_base_url=args.api_url,
            consensus_window=args.consensus_window,
            agreement_count=args.agreement_count,
            track_expiry_seconds=args.track_expiry,
            max_tracks=args.max_tracks,
            iou_threshold=args.iou_threshold,
        )
    except ValueError as exc:
        print(f"invalid webcam configuration: {exc}", file=sys.stderr)
        return 2
    return runner.run()


if __name__ == "__main__":
    sys.exit(main())
