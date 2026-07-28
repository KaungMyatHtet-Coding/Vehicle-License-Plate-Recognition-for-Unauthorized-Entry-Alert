"""Schemas for transient still-image plate detection."""

from pydantic import BaseModel, ConfigDict


class BoundingBox(BaseModel):
    """Original-image pixel coordinates with exclusive right/bottom edges."""

    model_config = ConfigDict(extra="forbid")

    x1: int
    y1: int
    x2: int
    y2: int


class PlateCropResponse(BaseModel):
    """Lossless in-memory crop encoded for transport."""

    model_config = ConfigDict(extra="forbid")

    media_type: str
    base64_data: str
    width: int
    height: int


class PlateDetectionResponse(BaseModel):
    """One detected plate and its original-pixel crop."""

    model_config = ConfigDict(extra="forbid")

    bbox: BoundingBox
    confidence: float
    label: str
    crop: PlateCropResponse


class ImageDetectionResponse(BaseModel):
    """Safe zero, one, or multiple plate detections for one validated image."""

    model_config = ConfigDict(extra="forbid")

    correlation_id: str
    status: str
    detection_count: int
    image_width: int
    image_height: int
    inference_ms: float
    total_ms: float
    detections: list[PlateDetectionResponse]
