"""Schemas for transient local OCR and conservative normalization."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class PlateOcrResponse(BaseModel):
    """One OCR result without authorization or persistence semantics."""

    model_config = ConfigDict(extra="forbid")

    correlation_id: str
    status: Literal["recognized", "manual_review"]
    review_reason: Literal["OCR_EMPTY", "OCR_LOW_CONFIDENCE"] | None
    raw_text: str
    normalized_text: str
    confidence: float | None
    mode: Literal["recognition_only", "full_pipeline"]
    inference_ms: float
    total_ms: float
    image_width: int
    image_height: int
