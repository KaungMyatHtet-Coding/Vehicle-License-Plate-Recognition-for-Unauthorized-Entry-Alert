"""Bounded, experimental short-video analysis without per-frame persistence."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
import logging
import math
import os
import tempfile
import time
from typing import TYPE_CHECKING

import cv2

from app.schemas.video import (
    VideoFrameDetection,
    VideoProcessingResponse,
    VideoProcessingTimings,
)

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.services.recognition_orchestration import (
        RecognitionAnalysis,
        RecognitionOrchestrationService,
    )

logger = logging.getLogger(__name__)

MAX_VIDEO_SIZE_BYTES = 25 * 1024 * 1024
MAX_VIDEO_DURATION_SECONDS = 10.0
ALLOWED_EXTENSIONS = (".mp4", ".avi", ".mov")
DEFAULT_TARGET_FPS = 2.0
DEFAULT_COOLDOWN_SECONDS = 3.0


class VideoValidationError(RuntimeError):
    """Sanitized failure for invalid or unsuccessfully persisted video work."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class _VideoObservation:
    """Private association of one analysis with its exact source frame."""

    frame_index: int
    timestamp_seconds: float
    frame_bytes: bytes
    analysis: RecognitionAnalysis


class VideoProcessingService:
    """Analyze a bounded upload and persist only one finalized consensus."""

    def __init__(
        self,
        orchestration: RecognitionOrchestrationService,
        settings: Settings | None = None,
        target_fps: float | None = None,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
    ) -> None:
        self._orchestration = orchestration
        self._settings = settings
        self._target_fps = target_fps
        self._cooldown_seconds = cooldown_seconds

    def _setting(self, name: str, default: object) -> object:
        if self._settings is not None:
            return getattr(self._settings, name)
        return default

    def process_video(
        self,
        video_bytes: bytes,
        filename: str,
        correlation_id: str,
    ) -> VideoProcessingResponse:
        started = time.perf_counter()
        self._validate_upload(video_bytes, filename)
        suffix = os.path.splitext(filename)[1].lower()
        tmp_path: str | None = None
        cap: cv2.VideoCapture | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
                tmp_path = tmp_file.name
                tmp_file.write(video_bytes)

            try:
                cap = cv2.VideoCapture(tmp_path)
            except Exception as exc:
                raise VideoValidationError(
                    "VIDEO_CORRUPT", "The uploaded video could not be decoded."
                ) from exc
            if not cap.isOpened():
                raise VideoValidationError(
                    "VIDEO_CORRUPT", "The uploaded video could not be decoded."
                )

            try:
                total_frames, fps, duration, step = self._validate_metadata(cap)
            except VideoValidationError:
                raise
            except Exception as exc:
                raise VideoValidationError(
                    "VIDEO_METADATA_INVALID",
                    "The uploaded video metadata is invalid.",
                ) from exc
            observations: deque[_VideoObservation] = deque(
                maxlen=int(self._setting("video_consensus_window_frames", 8))
            )
            sampled_count = 0
            decoded_count = 0
            extraction_ms = 0.0
            recognition_ms = 0.0
            while True:
                try:
                    ret, frame = cap.read()
                except Exception as exc:
                    raise VideoValidationError(
                        "VIDEO_DECODE_FAILED", "A video frame could not be decoded."
                    ) from exc
                if not ret:
                    break
                if decoded_count >= int(self._setting("video_max_decoded_frames", 300)):
                    raise VideoValidationError(
                        "VIDEO_FRAME_LIMIT",
                        "The video exceeds the decoded-frame limit.",
                    )
                frame_index = decoded_count
                decoded_count += 1
                if frame_index % step != 0:
                    continue
                if sampled_count >= int(self._setting("video_max_sampled_frames", 20)):
                    raise VideoValidationError(
                        "VIDEO_SAMPLE_LIMIT",
                        "The video exceeds the sampled-frame limit.",
                    )
                try:
                    height, width = frame.shape[:2]
                except Exception as exc:
                    raise VideoValidationError(
                        "VIDEO_FRAME_INVALID", "A video frame is invalid."
                    ) from exc
                max_width = int(self._setting("video_max_frame_width", 1920))
                max_height = int(self._setting("video_max_frame_height", 1080))
                max_pixels = int(self._setting("video_max_frame_pixels", 2_073_600))
                if (
                    width <= 0
                    or height <= 0
                    or width > max_width
                    or height > max_height
                ):
                    raise VideoValidationError(
                        "VIDEO_DIMENSIONS_INVALID",
                        "The video frame dimensions are invalid.",
                    )
                if width * height > max_pixels:
                    raise VideoValidationError(
                        "VIDEO_DIMENSIONS_INVALID", "The video frame is too large."
                    )
                extract_started = time.perf_counter()
                try:
                    ok, encoded = cv2.imencode(".jpg", frame)
                except Exception as exc:
                    raise VideoValidationError(
                        "VIDEO_FRAME_INVALID", "A video frame could not be encoded."
                    ) from exc
                extraction_ms += (time.perf_counter() - extract_started) * 1000
                if not ok:
                    raise VideoValidationError(
                        "VIDEO_FRAME_INVALID", "A video frame could not be encoded."
                    )
                frame_bytes = encoded.tobytes()
                recognition_started = time.perf_counter()
                try:
                    analysis = self._orchestration.analyze(frame_bytes, correlation_id)
                except Exception as exc:
                    raise VideoValidationError(
                        "VIDEO_ANALYSIS_FAILED",
                        "Video recognition could not be completed safely.",
                        503,
                    ) from exc
                recognition_ms += (time.perf_counter() - recognition_started) * 1000
                observations.append(
                    _VideoObservation(
                        frame_index=frame_index,
                        timestamp_seconds=round(frame_index / fps, 3),
                        frame_bytes=frame_bytes,
                        analysis=analysis,
                    )
                )
                sampled_count += 1

            if decoded_count == 0 or sampled_count == 0:
                raise VideoValidationError(
                    "VIDEO_NO_FRAMES", "The uploaded video contains no readable frames."
                )
            finalized = self._finalize_consensus(tuple(observations))
            detections = self._public_outcome(
                finalized, sampled_count, tuple(observations)
            )
            if finalized is not None:
                try:
                    persisted = self._orchestration._persist_analysis(
                        finalized.frame_bytes,
                        finalized.analysis,
                        correlation_id,
                        validate_identity=True,
                    )
                except Exception as exc:
                    raise VideoValidationError(
                        "VIDEO_PERSISTENCE_FAILED",
                        "The finalized video result could not be persisted.",
                        503,
                    ) from exc
                if persisted.logging is None or not persisted.logging.log_persisted:
                    raise VideoValidationError(
                        "VIDEO_PERSISTENCE_FAILED",
                        "The finalized video result could not be persisted.",
                        503,
                    )
                detections = [
                    VideoFrameDetection(
                        frame_index=finalized.frame_index,
                        timestamp_seconds=finalized.timestamp_seconds,
                        status="completed",
                        normalized_plate=finalized.analysis.ocr.normalized_text,
                        decision=persisted.logging.decision.decision,
                        reason=persisted.logging.decision.reason,
                        suppressed_as_duplicate=False,
                    )
                ]

            total_ms = round((time.perf_counter() - started) * 1000, 3)
            return VideoProcessingResponse(
                correlation_id=correlation_id,
                filename=os.path.basename(filename),
                total_frames_analyzed=sampled_count,
                duration_seconds=duration,
                fps=round(fps, 2),
                unique_plates_count=(1 if finalized is not None else 0),
                detections=detections,
                timings=VideoProcessingTimings(
                    extraction_ms=round(extraction_ms, 3),
                    recognition_ms=round(recognition_ms, 3),
                    total_ms=total_ms,
                ),
            )
        finally:
            if cap is not None:
                cap.release()
            if tmp_path is not None:
                try:
                    os.remove(tmp_path)
                except OSError:
                    logger.warning(
                        "Temporary video cleanup failed category=VIDEO_CLEANUP"
                    )

    def _validate_upload(self, video_bytes: bytes, filename: str) -> None:
        if not filename or not os.path.basename(filename):
            raise VideoValidationError(
                "VIDEO_FILENAME_REQUIRED", "A video filename is required."
            )
        max_size = int(self._setting("video_max_upload_bytes", MAX_VIDEO_SIZE_BYTES))
        if not video_bytes:
            raise VideoValidationError(
                "VIDEO_EMPTY", "The uploaded video file is empty."
            )
        if len(video_bytes) > max_size:
            raise VideoValidationError(
                "VIDEO_OVERSIZED", "The uploaded video exceeds the size limit."
            )
        ext = os.path.splitext(filename)[1].lower()
        allowed = tuple(
            self._setting("video_allowed_extensions", list(ALLOWED_EXTENSIONS))
        )
        if ext not in allowed:
            raise VideoValidationError(
                "VIDEO_FORMAT_UNSUPPORTED", "The uploaded video format is unsupported."
            )

    def _validate_metadata(
        self, cap: cv2.VideoCapture
    ) -> tuple[int, float, float, int]:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        if total_frames == 0:
            raise VideoValidationError(
                "VIDEO_NO_FRAMES", "The uploaded video contains no readable frames."
            )
        if total_frames < 0 or not math.isfinite(fps) or fps <= 0 or fps > 240:
            raise VideoValidationError(
                "VIDEO_METADATA_INVALID", "The uploaded video metadata is invalid."
            )
        duration = total_frames / fps
        max_duration = float(
            self._setting("video_max_duration_seconds", MAX_VIDEO_DURATION_SECONDS)
        )
        if duration <= 0 or duration > max_duration:
            raise VideoValidationError(
                "VIDEO_DURATION_EXCEEDED",
                "The uploaded video exceeds the duration limit.",
            )
        if total_frames > int(self._setting("video_max_decoded_frames", 300)):
            raise VideoValidationError(
                "VIDEO_FRAME_LIMIT", "The video exceeds the decoded-frame limit."
            )
        target_fps = self._target_fps or float(
            self._setting("video_target_fps", DEFAULT_TARGET_FPS)
        )
        target_step = max(1, int(round(fps / target_fps)))
        sample_step = max(
            target_step,
            (total_frames + int(self._setting("video_max_sampled_frames", 20)) - 1)
            // int(self._setting("video_max_sampled_frames", 20)),
        )
        return total_frames, fps, round(duration, 2), sample_step

    @staticmethod
    def _reliable_observation(observation: _VideoObservation) -> bool:
        ocr = observation.analysis.ocr
        return bool(
            observation.analysis.selected is not None
            and ocr is not None
            and ocr.status == "recognized"
            and ocr.normalized_text
        )

    def _finalize_consensus(
        self, observations: tuple[_VideoObservation, ...]
    ) -> _VideoObservation | None:
        reliable = [item for item in observations if self._reliable_observation(item)]
        if not reliable:
            return None
        plates = {item.analysis.ocr.normalized_text for item in reliable}
        if len(plates) != 1:
            return None
        required = int(self._setting("video_consensus_min_observations", 2))
        counts = Counter(item.analysis.ocr.normalized_text for item in reliable)
        plate, count = counts.most_common(1)[0]
        if count < required:
            return None
        matching = [
            item for item in reliable if item.analysis.ocr.normalized_text == plate
        ]
        return max(
            matching,
            key=lambda item: (
                item.analysis.ocr.confidence or 0.0,
                item.analysis.selected.confidence,
                -item.frame_index,
            ),
        )

    @staticmethod
    def _public_outcome(
        finalized: _VideoObservation | None,
        sampled_count: int,
        observations: tuple[_VideoObservation, ...],
    ) -> list[VideoFrameDetection]:
        if finalized is None:
            no_plate = all(item.analysis.selected is None for item in observations)
            return [
                VideoFrameDetection(
                    frame_index=sampled_count - 1,
                    timestamp_seconds=0.0,
                    status="no_plate_detected" if no_plate else "completed",
                    normalized_plate=None,
                    decision=None if no_plate else "MANUAL_REVIEW",
                    reason=None if no_plate else "VIDEO_CONSENSUS_UNRESOLVED",
                    suppressed_as_duplicate=False,
                )
            ]
        return []
