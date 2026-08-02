"""Day 17 service for bounded short video frame sampling and duplicate suppression."""

from __future__ import annotations

import logging
import os
import tempfile
import time
from typing import TYPE_CHECKING, Sequence

import cv2

from app.schemas.video import (
    VideoFrameDetection,
    VideoProcessingResponse,
    VideoProcessingTimings,
)

if TYPE_CHECKING:
    from app.services.recognition_orchestration import RecognitionOrchestrationService

logger = logging.getLogger(__name__)

MAX_VIDEO_SIZE_BYTES = 25 * 1024 * 1024  # 25 MiB
MAX_VIDEO_DURATION_SECONDS = 10.0
ALLOWED_EXTENSIONS: Sequence[str] = (".mp4", ".avi", ".mov")
DEFAULT_TARGET_FPS = 2.0
DEFAULT_COOLDOWN_SECONDS = 3.0


class VideoValidationError(RuntimeError):
    """Sanitized failure for invalid video uploads."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class VideoProcessingService:
    """Processes bounded video files by sampling frames and recognizing license plates."""

    def __init__(
        self,
        orchestration: RecognitionOrchestrationService,
        target_fps: float = DEFAULT_TARGET_FPS,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
    ) -> None:
        self._orchestration = orchestration
        self._target_fps = target_fps
        self._cooldown_seconds = cooldown_seconds

    def process_video(
        self,
        video_bytes: bytes,
        filename: str,
        correlation_id: str,
    ) -> VideoProcessingResponse:
        started = time.perf_counter()

        if not video_bytes:
            raise VideoValidationError(
                "VIDEO_EMPTY", "The uploaded video file is empty."
            )

        if len(video_bytes) > MAX_VIDEO_SIZE_BYTES:
            raise VideoValidationError(
                "VIDEO_OVERSIZED",
                f"The video file size exceeds the maximum limit of {MAX_VIDEO_SIZE_BYTES // (1024 * 1024)} MiB.",
            )

        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise VideoValidationError(
                "VIDEO_FORMAT_UNSUPPORTED",
                f"Unsupported video format '{ext}'. Allowed formats: {', '.join(ALLOWED_EXTENSIONS)}.",
            )

        suffix = ext if ext else ".mp4"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
            tmp_path = tmp_file.name
            tmp_file.write(video_bytes)

        extraction_ms = 0.0
        recognition_ms = 0.0
        cap: cv2.VideoCapture | None = None

        try:
            cap = cv2.VideoCapture(tmp_path)
            if not cap.isOpened():
                raise VideoValidationError(
                    "VIDEO_CORRUPT", "Failed to open or decode the video file."
                )

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            if fps <= 0 or total_frames <= 0:
                raise VideoValidationError(
                    "VIDEO_CORRUPT",
                    "Invalid video metadata: unable to determine frame rate or count.",
                )

            duration = round(total_frames / fps, 2)
            if duration > MAX_VIDEO_DURATION_SECONDS:
                raise VideoValidationError(
                    "VIDEO_DURATION_EXCEEDED",
                    f"Video duration ({duration}s) exceeds maximum allowed limit of {MAX_VIDEO_DURATION_SECONDS}s.",
                )

            step = max(1, int(round(fps / self._target_fps)))
            frame_detections: list[VideoFrameDetection] = []
            last_seen_times: dict[str, float] = {}

            sample_indices = list(range(0, total_frames, step))
            for f_idx in sample_indices:
                t_extract_start = time.perf_counter()
                cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
                ret, frame = cap.read()
                extraction_ms += (time.perf_counter() - t_extract_start) * 1000

                if not ret or frame is None:
                    continue

                timestamp_sec = round(f_idx / fps, 2)
                t_rec_start = time.perf_counter()
                ok, encoded_img = cv2.imencode(".jpg", frame)
                if not ok:
                    recognition_ms += (time.perf_counter() - t_rec_start) * 1000
                    continue

                frame_bytes = encoded_img.tobytes()
                # Run through standard orchestration
                res = self._orchestration.recognize(frame_bytes, correlation_id)
                recognition_ms += (time.perf_counter() - t_rec_start) * 1000

                if res.status == "no_plate_detected" or res.ocr is None:
                    frame_detections.append(
                        VideoFrameDetection(
                            frame_index=f_idx,
                            timestamp_seconds=timestamp_sec,
                            status="no_plate_detected",
                            normalized_plate=None,
                            decision=None,
                            reason=None,
                            suppressed_as_duplicate=False,
                        )
                    )
                else:
                    plate = res.ocr.normalized_text
                    decision = res.logging.decision.decision if res.logging else None
                    reason = res.logging.decision.reason if res.logging else None

                    suppressed = False
                    if plate in last_seen_times:
                        time_since_last = timestamp_sec - last_seen_times[plate]
                        if time_since_last < self._cooldown_seconds:
                            suppressed = True

                    if not suppressed:
                        last_seen_times[plate] = timestamp_sec

                    frame_detections.append(
                        VideoFrameDetection(
                            frame_index=f_idx,
                            timestamp_seconds=timestamp_sec,
                            status="completed",
                            normalized_plate=plate,
                            decision=decision,
                            reason=reason,
                            suppressed_as_duplicate=suppressed,
                        )
                    )

        finally:
            if cap is not None:
                cap.release()
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    logger.warning(
                        "Failed to remove temporary video file: %s", tmp_path
                    )

        total_ms = round((time.perf_counter() - started) * 1000, 3)
        unique_plates = len(
            {
                d.normalized_plate
                for d in frame_detections
                if d.normalized_plate is not None
            }
        )

        return VideoProcessingResponse(
            correlation_id=correlation_id,
            filename=filename,
            total_frames_analyzed=len(frame_detections),
            duration_seconds=duration,
            fps=round(fps, 2),
            unique_plates_count=unique_plates,
            detections=frame_detections,
            timings=VideoProcessingTimings(
                extraction_ms=round(extraction_ms, 3),
                recognition_ms=round(recognition_ms, 3),
                total_ms=total_ms,
            ),
        )
