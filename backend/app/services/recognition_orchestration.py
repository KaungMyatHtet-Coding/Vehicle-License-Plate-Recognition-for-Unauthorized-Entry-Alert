"""Day 13 composition of the existing recognition service boundaries."""

from __future__ import annotations

import base64
import binascii
import time
from typing import Protocol

from app.schemas.detection import ImageDetectionResponse
from app.schemas.recognition import RecognitionResponse, RecognitionTimings
from app.services.detection_logging import DetectionLoggingService
from app.services.ocr_recognition import PlateOcrService
from app.services.plate_detection import PlateDetectionService
from app.services.authorization_decision import AuthorizationDecisionService


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
    ) -> None:
        self._detector = detector
        self._ocr = ocr
        self._decision = decision
        self._logging = logging

    def recognize(self, image_bytes: bytes, correlation_id: str) -> RecognitionResponse:
        started = time.perf_counter()
        detection = self._detector.detect(image_bytes, correlation_id)
        if detection.status == "no_plate_detected":
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
            logging=logging,
            timings=RecognitionTimings(
                detection_ms=detection.total_ms,
                ocr_ms=ocr.total_ms,
                total_ms=total_ms,
            ),
        )
