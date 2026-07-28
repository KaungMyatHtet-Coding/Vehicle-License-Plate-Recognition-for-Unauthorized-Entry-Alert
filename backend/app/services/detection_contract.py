"""Shared plate-localization contract established by the Day 4 evaluation."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PlateDetection:
    """A validated plate-localization result in original-image coordinates."""

    bbox: tuple[int, int, int, int]
    confidence: float
    label: str

    def __post_init__(self) -> None:
        if not isinstance(self.bbox, tuple) or len(self.bbox) != 4:
            raise TypeError("bbox must be a tuple of four integers")
        if any(type(value) is not int for value in self.bbox):
            raise TypeError("bbox coordinates must be integers")

        x1, y1, x2, y2 = self.bbox
        if x1 < 0 or y1 < 0:
            raise ValueError("bbox coordinates must be non-negative")
        if x2 <= x1 or y2 <= y1:
            raise ValueError("bbox must have positive width and height")

        if type(self.confidence) is not float:
            raise TypeError("confidence must be a float")
        if not math.isfinite(self.confidence):
            raise ValueError("confidence must be finite")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")

        if not isinstance(self.label, str):
            raise TypeError("label must be a string")
        if not self.label.strip():
            raise ValueError("label must not be empty")


def validate_detection_bounds(
    detection: PlateDetection, image_width: int, image_height: int
) -> None:
    """Require a detection to be clipped within positive image dimensions."""

    if type(image_width) is not int or type(image_height) is not int:
        raise TypeError("image dimensions must be integers")
    if image_width <= 0 or image_height <= 0:
        raise ValueError("image dimensions must be positive")

    _, _, x2, y2 = detection.bbox
    if x2 > image_width or y2 > image_height:
        raise ValueError("bbox must be clipped to the original image bounds")
