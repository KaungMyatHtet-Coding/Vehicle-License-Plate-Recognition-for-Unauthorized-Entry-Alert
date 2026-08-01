"""Authoritative Day 13 still-image recognition response."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.detection import PlateDetectionResponse
from app.schemas.logging import DecisionAuditSnapshot, LoggingFailureCode
from app.schemas.ocr import PlateOcrResponse


class RecognitionTimings(BaseModel):
    """Measured processing stages exposed without implementation details."""

    model_config = ConfigDict(extra="forbid")

    detection_ms: float
    ocr_ms: float
    total_ms: float


class PublicLoggingResult(BaseModel):
    """Sanitized logging outcome without private storage coordinates or grants."""

    model_config = ConfigDict(extra="forbid")

    decision: DecisionAuditSnapshot
    status: Literal["completed", "partial_failure"]
    failures: tuple[LoggingFailureCode, ...]
    log_persisted: bool
    evidence_available: bool
    completed_at: str


class RecognitionResponse(BaseModel):
    """One authoritative no-plate or decided recognition outcome."""

    model_config = ConfigDict(extra="forbid")

    correlation_id: str
    status: Literal["no_plate_detected", "completed"]
    message: str
    detection_count: int
    selected_plate: PlateDetectionResponse | None
    ocr: PlateOcrResponse | None
    logging: PublicLoggingResult | None
    timings: RecognitionTimings
