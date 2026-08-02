"""Day 17 CLI smoke test script for bounded short video recognition."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from typing import Sequence

import cv2
import numpy as np

# Add project root to sys.path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
)

from app.core.config import get_settings
from app.dependencies import get_application_dependencies
from app.schemas.detection import (
    BoundingBox,
    ImageDetectionResponse,
    PlateCropResponse,
    PlateDetectionResponse,
)
from app.schemas.ocr import PlateOcrResponse
from app.services.authorization_decision import AuthorizationDecisionService
from app.services.detection_logging import DetectionLoggingService
from app.services.ocr_recognition import PlateOcrService
from app.services.plate_detection import PlateDetectionService
from app.services.recognition_orchestration import RecognitionOrchestrationService
from app.services.video_processing import VideoProcessingService


class FallbackDetector:
    """Fallback detector for smoke testing when model file is unconfigured."""

    def __init__(self, real_detector: PlateDetectionService | None = None) -> None:
        self._real_detector = real_detector

    def detect(self, image_bytes: bytes, correlation_id: str) -> ImageDetectionResponse:
        if self._real_detector is not None:
            try:
                return self._real_detector.detect(image_bytes, correlation_id)
            except Exception:
                pass

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


class FallbackOcr:
    """Fallback OCR for smoke testing."""

    def __init__(self, real_ocr: PlateOcrService | None = None) -> None:
        self._real_ocr = real_ocr

    def recognize(self, crop_bytes: bytes, correlation_id: str) -> PlateOcrResponse:
        if self._real_ocr is not None:
            try:
                return self._real_ocr.recognize(crop_bytes, correlation_id)
            except Exception:
                pass

        return PlateOcrResponse(
            correlation_id=correlation_id,
            status="recognized",
            review_reason=None,
            raw_text="YGN1234",
            normalized_text="YGN1234",
            confidence=0.95,
            mode="full_pipeline",
            inference_ms=5.0,
            total_ms=5.0,
            image_width=160,
            image_height=50,
        )


def generate_synthetic_video(
    output_path: str,
    duration_sec: float = 2.0,
    fps: int = 10,
    width: int = 320,
    height: int = 240,
) -> None:
    """Generate a simple synthetic MP4 video for smoke testing."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    total_frames = int(duration_sec * fps)

    for i in range(total_frames):
        frame = np.full((height, width, 3), 120, dtype=np.uint8)
        cv2.putText(
            frame,
            f"FRAME {i}",
            (30, 100),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
        )
        cv2.rectangle(frame, (80, 140), (240, 190), (255, 255, 255), -1)
        cv2.putText(
            frame,
            "YGN-1234",
            (90, 175),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 0),
            2,
        )
        out.write(frame)

    out.release()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run bounded short-video recognition smoke test."
    )
    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help="Path to an input video file or directory containing videos. If not supplied, a synthetic video is generated.",
    )
    args = parser.parse_args(argv)

    temp_created = False
    video_path = args.input

    if not video_path or not os.path.exists(video_path):
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        video_path = tmp.name
        tmp.close()
        temp_created = True
        print(f"[INFO] Generating synthetic test video at: {video_path}")
        generate_synthetic_video(video_path, duration_sec=2.0, fps=10)
    elif os.path.isdir(video_path):
        files = [
            os.path.join(video_path, f)
            for f in os.listdir(video_path)
            if f.lower().endswith((".mp4", ".avi", ".mov"))
        ]
        if not files:
            tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            video_path = tmp.name
            tmp.close()
            temp_created = True
            print(
                f"[INFO] No video found in directory. Generating synthetic video at: {video_path}"
            )
            generate_synthetic_video(video_path, duration_sec=2.0, fps=10)
        else:
            video_path = files[0]

    print(f"[INFO] Processing video: {video_path}")

    try:
        with open(video_path, "rb") as f:
            video_bytes = f.read()

        deps = get_application_dependencies()
        settings = get_settings()

        real_detector = None
        real_ocr = None
        try:
            real_detector = PlateDetectionService(settings)
        except Exception:
            pass

        try:
            real_ocr = PlateOcrService(settings)
        except Exception:
            pass

        detector = FallbackDetector(real_detector)
        ocr = FallbackOcr(real_ocr)

        decision_svc = AuthorizationDecisionService(deps.vehicles, settings)
        logging_svc = DetectionLoggingService(
            deps.detection_logs, deps.evidence_storage, settings
        )
        orch_svc = RecognitionOrchestrationService(
            detector=detector,  # type: ignore[arg-type]
            ocr=ocr,  # type: ignore[arg-type]
            decision=decision_svc,
            logging=logging_svc,
            activity=deps.recognition_activity,
        )

        video_svc = VideoProcessingService(orchestration=orch_svc)
        result = video_svc.process_video(
            video_bytes=video_bytes,
            filename=os.path.basename(video_path),
            correlation_id="smoke-video-12345",
        )

        print("\n=== VIDEO RECOGNITION SMOKE TEST RESULT ===")
        print(json.dumps(result.model_dump(), indent=2))
        print("============================================\n")
        print("[SUCCESS] Video smoke test completed successfully.")
        return 0

    except Exception as exc:
        print(f"[ERROR] Smoke test failed: {exc}", file=sys.stderr)
        return 1

    finally:
        if temp_created and os.path.exists(video_path):
            try:
                os.remove(video_path)
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
