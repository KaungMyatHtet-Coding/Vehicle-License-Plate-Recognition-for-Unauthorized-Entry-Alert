"""Day 17 Pydantic schemas for bounded short video processing."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class VideoFrameDetection(BaseModel):
    """Detection outcome for a single sampled video frame."""

    model_config = ConfigDict(extra="forbid")

    frame_index: int
    timestamp_seconds: float
    status: Literal["no_plate_detected", "completed"]
    normalized_plate: str | None
    decision: str | None
    reason: str | None
    suppressed_as_duplicate: bool


class VideoProcessingTimings(BaseModel):
    """Performance metrics for video frame extraction and recognition."""

    model_config = ConfigDict(extra="forbid")

    extraction_ms: float
    recognition_ms: float
    total_ms: float


class VideoProcessingResponse(BaseModel):
    """Authoritative summary of a processed video file."""

    model_config = ConfigDict(extra="forbid")

    correlation_id: str
    filename: str
    total_frames_analyzed: int
    duration_seconds: float
    fps: float
    unique_plates_count: int
    detections: list[VideoFrameDetection]
    timings: VideoProcessingTimings
