"""Authoritative Day 13 still-image recognition response."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.detection import PlateDetectionResponse
from app.schemas.logging import DetectionLoggingResult
from app.schemas.ocr import PlateOcrResponse


class RecognitionTimings(BaseModel):
    """Measured processing stages exposed without implementation details."""

    model_config = ConfigDict(extra="forbid")

    detection_ms: float
    ocr_ms: float
    total_ms: float


class RecognitionResponse(BaseModel):
    """One authoritative no-plate or decided recognition outcome."""

    model_config = ConfigDict(extra="forbid")

    correlation_id: str
    status: Literal["no_plate_detected", "completed"]
    message: str
    detection_count: int
    selected_plate: PlateDetectionResponse | None
    ocr: PlateOcrResponse | None
    logging: DetectionLoggingResult | None
    timings: RecognitionTimings
