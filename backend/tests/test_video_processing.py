"""Day 17 unit and integration tests for bounded short video processing."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from typing import Generator

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_application_dependencies
from app.main import app
from app.schemas.detection import (
    BoundingBox,
    ImageDetectionResponse,
    PlateCropResponse,
    PlateDetectionResponse,
)
from app.schemas.ocr import PlateOcrResponse
from app.services.video_processing import (
    MAX_VIDEO_SIZE_BYTES,
    VideoProcessingService,
    VideoValidationError,
)

client = TestClient(app)


class MockDetector:
    """Mock detector returning a fixed detection."""

    def detect(self, image_bytes: bytes, correlation_id: str) -> ImageDetectionResponse:
        return ImageDetectionResponse(
            correlation_id=correlation_id,
            status="completed",
            detection_count=1,
            image_width=320,
            image_height=240,
            inference_ms=10.0,
            total_ms=10.0,
            detections=[
                PlateDetectionResponse(
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
            ],
        )


class MockOcr:
    """Mock OCR returning a fixed plate text."""

    def __init__(
        self, normalized_text: str = "YGN1234", confidence: float = 0.95
    ) -> None:
        self._normalized_text = normalized_text
        self._confidence = confidence

    def recognize(self, crop_bytes: bytes, correlation_id: str) -> PlateOcrResponse:
        return PlateOcrResponse(
            correlation_id=correlation_id,
            status="recognized",
            review_reason=None,
            raw_text=self._normalized_text,
            normalized_text=self._normalized_text,
            confidence=self._confidence,
            mode="full_pipeline",
            inference_ms=5.0,
            total_ms=5.0,
            image_width=160,
            image_height=50,
        )


def generate_test_video_bytes(duration_sec: float = 2.0, fps: int = 10) -> bytes:
    """Generate in-memory MP4 video bytes for testing."""
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp_path = tmp.name
    tmp.close()

    try:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(tmp_path, fourcc, fps, (320, 240))
        total_frames = int(duration_sec * fps)

        for i in range(total_frames):
            frame = np.full((240, 320, 3), 100, dtype=np.uint8)
            cv2.putText(
                frame,
                f"F{i}",
                (50, 120),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (255, 255, 255),
                2,
            )
            out.write(frame)

        out.release()

        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@pytest.fixture(autouse=True)
def reset_dependencies() -> Generator[None, None, None]:
    deps = get_application_dependencies()
    if hasattr(deps.vehicles, "clear"):
        deps.vehicles.clear()
    elif hasattr(deps.vehicles, "_records"):
        deps.vehicles._records.clear()

    if hasattr(deps.detection_logs, "clear"):
        deps.detection_logs.clear()
    elif hasattr(deps.detection_logs, "_records"):
        deps.detection_logs._records.clear()

    if hasattr(deps.recognition_activity, "_records"):
        deps.recognition_activity._records.clear()
    if hasattr(deps.evidence_storage, "_objects"):
        deps.evidence_storage._objects.clear()
    if hasattr(deps.evidence_storage, "_grants"):
        deps.evidence_storage._grants.clear()
    yield
    app.dependency_overrides.clear()


def test_video_validation_empty_oversized_unsupported_duration() -> None:
    deps = get_application_dependencies()
    from app.core.config import get_settings
    from app.services.authorization_decision import AuthorizationDecisionService
    from app.services.detection_logging import DetectionLoggingService
    from app.services.recognition_orchestration import RecognitionOrchestrationService

    settings = get_settings()
    orch_svc = RecognitionOrchestrationService(
        detector=MockDetector(),  # type: ignore[arg-type]
        ocr=MockOcr(),  # type: ignore[arg-type]
        decision=AuthorizationDecisionService(deps.vehicles, settings),
        logging=DetectionLoggingService(
            deps.detection_logs, deps.evidence_storage, settings
        ),
    )
    svc = VideoProcessingService(orchestration=orch_svc)

    # 1. Empty bytes
    with pytest.raises(VideoValidationError) as exc1:
        svc.process_video(b"", "video.mp4", "cid-1")
    assert exc1.value.code == "VIDEO_EMPTY"

    # 2. Oversized bytes
    large_bytes = b"x" * (MAX_VIDEO_SIZE_BYTES + 1)
    with pytest.raises(VideoValidationError) as exc2:
        svc.process_video(large_bytes, "video.mp4", "cid-2")
    assert exc2.value.code == "VIDEO_OVERSIZED"

    # 3. Unsupported format
    with pytest.raises(VideoValidationError) as exc3:
        svc.process_video(b"fakecontent", "video.txt", "cid-3")
    assert exc3.value.code == "VIDEO_FORMAT_UNSUPPORTED"

    # 4. Excessive duration (>10s)
    long_video_bytes = generate_test_video_bytes(duration_sec=11.0, fps=10)
    with pytest.raises(VideoValidationError) as exc4:
        svc.process_video(long_video_bytes, "video.mp4", "cid-4")
    assert exc4.value.code == "VIDEO_DURATION_EXCEEDED"


def test_video_processing_frame_sampling_and_duplicate_suppression() -> None:
    deps = get_application_dependencies()
    from app.core.config import get_settings
    from app.services.authorization_decision import AuthorizationDecisionService
    from app.services.detection_logging import DetectionLoggingService
    from app.services.recognition_orchestration import RecognitionOrchestrationService

    settings = get_settings()
    orch_svc = RecognitionOrchestrationService(
        detector=MockDetector(),  # type: ignore[arg-type]
        ocr=MockOcr(normalized_text="YGN1234"),  # type: ignore[arg-type]
        decision=AuthorizationDecisionService(deps.vehicles, settings),
        logging=DetectionLoggingService(
            deps.detection_logs, deps.evidence_storage, settings
        ),
    )
    svc = VideoProcessingService(
        orchestration=orch_svc, target_fps=2.0, cooldown_seconds=3.0
    )

    video_bytes = generate_test_video_bytes(duration_sec=2.0, fps=10)
    result = svc.process_video(video_bytes, "sample.mp4", correlation_id="cid-dup-test")

    assert result.correlation_id == "cid-dup-test"
    assert result.filename == "sample.mp4"
    assert result.duration_seconds == 2.0
    assert result.fps == 10.0
    assert result.total_frames_analyzed == 4  # frames 0, 5, 10, 15 sampled
    assert result.unique_plates_count == 1

    # First frame (0s) should not be suppressed
    assert result.detections[0].normalized_plate == "YGN1234"
    assert result.detections[0].suppressed_as_duplicate is False

    # Subsequent frames within 3.0s should be suppressed as duplicate
    for det in result.detections[1:]:
        assert det.normalized_plate == "YGN1234"
        assert det.suppressed_as_duplicate is True


def test_api_analyze_video_endpoint_is_disabled_by_default() -> None:
    res = client.post("/api/recognition/analyze-video")
    assert res.status_code == 404


def test_api_analyze_video_opt_in_registers_route_and_sanitizes_errors() -> None:
    """Verify opt-in behavior in a fresh process without changing the global app."""
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
            """
from fastapi.testclient import TestClient
from app.main import app

path = "/api/recognition/analyze-video"
response = TestClient(app).post(
    path, files={"file": ("document.pdf", b"not-a-video", "application/pdf")}
)
print(path in app.openapi()["paths"])
print(response.status_code, response.json()["error"]["code"])
""",
        ],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )

    assert probe.stdout.splitlines() == ["True", "400 VIDEO_FORMAT_UNSUPPORTED"]
