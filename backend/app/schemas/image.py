"""Schemas for transient image-input validation."""

from pydantic import BaseModel, ConfigDict


class ImageValidationResponse(BaseModel):
    """Metadata returned after an image passes validation."""

    model_config = ConfigDict(extra="forbid")

    correlation_id: str
    filename: str
    content_type: str
    detected_format: str
    size_bytes: int
    width: int
    height: int
