"""Day 13 composition of the existing recognition service boundaries."""

from __future__ import annotations

import base64
import binascii
import logging
import time
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from app.schemas.detection import ImageDetectionResponse
from app.repositories.contracts import RecognitionActivityRepository
from app.schemas.recognition import (
    PublicLoggingResult,
    RecognitionResponse,
    RecognitionTimings,
)
from app.services.detection_logging import DetectionLoggingService
from app.services.ocr_recognition import PlateOcrService
from app.services.plate_detection import PlateDetectionService
from app.services.authorization_decision import AuthorizationDecisionService

logger = logging.getLogger(__name__)


class Detector(Protocol):
    def detect(
        self, image_bytes: bytes, correlation_id: str
    ) -> ImageDetectionResponse: ...


class RecognitionOrchestrationError(RuntimeError):
    """Sanitized failure at the composition boundary."""

    def __init__(self, code: str, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class RecognitionOrchestrationService:
    """Run one validated image through Days 5–11 without changing their rules."""

    def __init__(
        self,
        detector: PlateDetectionService,
        ocr: PlateOcrService,
        decision: AuthorizationDecisionService,
        logging: DetectionLoggingService,
        activity: RecognitionActivityRepository | None = None,
    ) -> None:
        self._detector = detector
        self._ocr = ocr
        self._decision = decision
        self._logging = logging
        self._activity = activity

    def recognize(self, image_bytes: bytes, correlation_id: str) -> RecognitionResponse:
        started = time.perf_counter()
        detection = self._detector.detect(image_bytes, correlation_id)
        if detection.status == "no_plate_detected":
            if self._activity is not None:
                try:
                    self._activity.add_no_plate(
                        UUID(correlation_id), datetime.now(timezone.utc)
                    )
                except Exception:
                    logger.warning(
                        "No-plate activity persistence failed for correlation_id=%s category=NO_PLATE_ACTIVITY_PERSISTENCE_FAILED",
                        correlation_id,
                    )
            total_ms = round((time.perf_counter() - started) * 1000, 3)
            return RecognitionResponse(
                correlation_id=correlation_id,
                status="no_plate_detected",
                message="No license plate was detected; try another image or review it manually.",
                detection_count=0,
                selected_plate=None,
                ocr=None,
                logging=None,
                timings=RecognitionTimings(
                    detection_ms=detection.total_ms,
                    ocr_ms=0.0,
                    total_ms=total_ms,
                ),
            )

        if not detection.detections:
            raise RecognitionOrchestrationError(
                "DETECTION_RESULT_INVALID",
                "Plate detection returned an invalid result.",
            )
        selected = detection.detections[0]
        try:
            crop_bytes = base64.b64decode(selected.crop.base64_data, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise RecognitionOrchestrationError(
                "DETECTION_CROP_INVALID",
                "The detected plate crop could not be processed.",
            ) from exc

        ocr = self._ocr.recognize(crop_bytes, correlation_id)
        decision = self._decision.decide(ocr)
        logging = self._logging.persist(
            image_bytes=image_bytes,
            bbox=(
                selected.bbox.x1,
                selected.bbox.y1,
                selected.bbox.x2,
                selected.bbox.y2,
            ),
            ocr=ocr,
            decision=decision,
            timings={
                "detection_ms": detection.total_ms,
                "ocr_ms": ocr.total_ms,
            },
        )
        total_ms = round((time.perf_counter() - started) * 1000, 3)
        return RecognitionResponse(
            correlation_id=correlation_id,
            status="completed",
            message=decision.message,
            detection_count=detection.detection_count,
            selected_plate=selected,
            ocr=ocr,
            logging=PublicLoggingResult(
                decision=logging.decision,
                status=logging.status,
                failures=logging.failures,
                log_persisted=logging.log_persisted,
                evidence_available=logging.evidence is not None,
                completed_at=logging.completed_at.isoformat(),
            ),
            timings=RecognitionTimings(
                detection_ms=detection.total_ms,
                ocr_ms=ocr.total_ms,
                total_ms=total_ms,
            ),
        )
