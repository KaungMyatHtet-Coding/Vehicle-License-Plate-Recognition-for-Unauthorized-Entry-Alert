"""Deterministic, in-memory privacy-aware evidence annotation."""

from __future__ import annotations

import cv2
import numpy as np

from app.schemas.logging import DecisionAuditSnapshot


class EvidenceAnnotationError(RuntimeError):
    """Stable annotation failure without decoder or path details."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class EvidenceAnnotationService:
    """Draw a bounded plate box and minimal decision label into a fresh JPEG."""

    def annotate(
        self,
        image_bytes: bytes,
        bbox: tuple[int, int, int, int],
        decision: DecisionAuditSnapshot,
    ) -> bytes:
        if not isinstance(image_bytes, bytes) or not image_bytes:
            raise EvidenceAnnotationError(
                "EVIDENCE_IMAGE_INVALID",
                "The evidence image is invalid.",
            )
        image = cv2.imdecode(
            np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
        )
        if image is None:
            raise EvidenceAnnotationError(
                "EVIDENCE_IMAGE_INVALID",
                "The evidence image is invalid.",
            )
        height, width = image.shape[:2]
        if (
            not isinstance(bbox, tuple)
            or len(bbox) != 4
            or any(
                isinstance(value, bool) or not isinstance(value, int) for value in bbox
            )
        ):
            raise EvidenceAnnotationError(
                "EVIDENCE_BBOX_INVALID",
                "The evidence bounding box is invalid.",
            )
        x1, y1, x2, y2 = bbox
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise EvidenceAnnotationError(
                "EVIDENCE_BBOX_INVALID",
                "The evidence bounding box is invalid.",
            )

        annotated = image.copy()
        color = {
            "AUTHORIZED": (40, 160, 40),
            "UNAUTHORIZED": (40, 40, 200),
            "MANUAL_REVIEW": (0, 150, 220),
        }[decision.decision]
        cv2.rectangle(annotated, (x1, y1), (x2 - 1, y2 - 1), color, 2)
        label = f"{decision.decision} {decision.reason}"
        label_y = max(14, y1 - 6)
        cv2.putText(
            annotated,
            label,
            (x1, label_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            color,
            1,
            cv2.LINE_8,
        )
        success, encoded = cv2.imencode(
            ".jpg",
            annotated,
            [cv2.IMWRITE_JPEG_QUALITY, 90, cv2.IMWRITE_JPEG_OPTIMIZE, 0],
        )
        if not success:
            raise EvidenceAnnotationError(
                "EVIDENCE_ENCODING_FAILED",
                "The evidence image could not be encoded.",
            )
        return encoded.tobytes()
