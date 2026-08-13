"""Day 13 composition of the existing recognition service boundaries."""

from __future__ import annotations

import base64
import binascii
import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

import cv2
import numpy as np

from app.schemas.detection import ImageDetectionResponse
from app.repositories.contracts import RecognitionActivityRepository
from app.schemas.recognition import (
    PublicLoggingResult,
    RecognitionResponse,
    RecognitionTimings,
)
from app.services.detection_logging import DetectionLoggingService
from app.services.ocr_recognition import PlateOcrService
from app.services.ocr_recognition import is_plate_grammar_reliable, plate_review_reason
from app.services.plate_detection import PlateDetectionService
from app.services.authorization_decision import AuthorizationDecisionService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecognitionAnalysis:
    """Non-persisting result of detection, selection, and authorization."""

    detection: ImageDetectionResponse
    selected: object | None
    ocr: object | None
    decision: object | None
    detection_ms: float
    ocr_ms: float


@dataclass(frozen=True)
class _CandidateEvaluation:
    candidate: object
    ocr: object
    score: float
    reliable: bool


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

    _OCR_CROP_PADDING_RATIO = 1.0

    def __init__(
        self,
        detector: PlateDetectionService,
        ocr: PlateOcrService,
        decision: AuthorizationDecisionService,
        logging: DetectionLoggingService,
        activity: RecognitionActivityRepository | None = None,
        settings: object | None = None,
    ) -> None:
        self._detector = detector
        self._ocr = ocr
        self._decision = decision
        self._logging = logging
        self._activity = activity
        self._settings = settings

    def recognize(self, image_bytes: bytes, correlation_id: str) -> RecognitionResponse:
        """Analyze, decide, then persist exactly once for a still image."""

        analysis = self.analyze(image_bytes, correlation_id)
        return self._persist_analysis(
            image_bytes, analysis, correlation_id, validate_identity=False
        )

    def _persist_analysis(
        self,
        image_bytes: bytes,
        analysis: RecognitionAnalysis,
        correlation_id: str,
        *,
        validate_identity: bool = True,
    ) -> RecognitionResponse:
        """Persist one service-produced finalized analysis (private webcam boundary)."""

        if analysis.selected is None:
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
            total_ms = round((analysis.detection_ms + analysis.ocr_ms), 3)
            return RecognitionResponse(
                correlation_id=correlation_id,
                status="no_plate_detected",
                message="No license plate was detected; try another image or review it manually.",
                detection_count=0,
                selected_plate=None,
                ocr=None,
                logging=None,
                timings=RecognitionTimings(
                    detection_ms=analysis.detection_ms,
                    ocr_ms=analysis.ocr_ms,
                    total_ms=total_ms,
                ),
            )

        selected = analysis.selected
        ocr = analysis.ocr
        decision = analysis.decision
        assert selected is not None and ocr is not None and decision is not None
        if validate_identity and (
            getattr(ocr, "correlation_id", None) != correlation_id
            or getattr(decision, "correlation_id", None) != correlation_id
            or getattr(decision, "normalized_plate", None)
            != getattr(ocr, "normalized_text", None)
            or not getattr(ocr, "normalized_text", None)
        ):
            raise RecognitionOrchestrationError(
                "ANALYSIS_INVALID",
                "The finalized recognition analysis could not be persisted.",
            )
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
            timings={"detection_ms": analysis.detection_ms, "ocr_ms": analysis.ocr_ms},
        )
        total_ms = round(analysis.detection_ms + analysis.ocr_ms, 3)
        return RecognitionResponse(
            correlation_id=correlation_id,
            status="completed",
            message=decision.message,
            detection_count=analysis.detection.detection_count,
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
                detection_ms=analysis.detection_ms,
                ocr_ms=analysis.ocr_ms,
                total_ms=total_ms,
            ),
        )

    def analyze(self, image_bytes: bytes, correlation_id: str) -> RecognitionAnalysis:
        """Collect, rank, and decide candidates without logging or evidence."""

        detection = self._detector.detect(image_bytes, correlation_id)
        if detection.status == "no_plate_detected":
            return RecognitionAnalysis(
                detection, None, None, None, detection.total_ms, 0.0
            )

        if not detection.detections:
            raise RecognitionOrchestrationError(
                "DETECTION_RESULT_INVALID",
                "Plate detection returned an invalid result.",
            )
        settings = self._settings
        source_image = self._decode_source_image(image_bytes)
        max_candidates = getattr(settings, "max_recognition_candidates", 3)
        candidates = sorted(
            detection.detections,
            key=lambda item: self._candidate_order_key(item, detection),
        )[:max_candidates]
        evaluations: list[_CandidateEvaluation] = []
        ocr_started = time.perf_counter()
        for candidate in candidates:
            crop_bytes = self._ocr_crop_bytes(candidate, source_image)
            candidate_ocr = self._ocr.recognize(crop_bytes, correlation_id)
            grammar_ok = is_plate_grammar_reliable(
                candidate_ocr.normalized_text,
                getattr(settings, "supported_plate_regions", ["YGN", "MDY", "NPT"]),
                getattr(settings, "min_plate_length", 7),
                getattr(settings, "max_plate_length", 12),
            )
            reliable = (
                candidate_ocr.status == "recognized"
                and candidate_ocr.confidence is not None
                and candidate_ocr.confidence
                >= getattr(settings, "ocr_min_confidence", 0.80)
                and grammar_ok
            )
            score = self._candidate_score(
                candidate, candidate_ocr, grammar_ok, detection
            )
            if not reliable:
                reason = (
                    plate_review_reason(
                        candidate_ocr.normalized_text,
                        candidate_ocr.confidence,
                        getattr(
                            settings, "supported_plate_regions", ["YGN", "MDY", "NPT"]
                        ),
                        getattr(settings, "min_plate_length", 7),
                        getattr(settings, "max_plate_length", 12),
                        getattr(settings, "ocr_min_confidence", 0.80),
                    )
                    or "PLATE_TEXT_UNRELIABLE"
                )
                candidate_ocr = candidate_ocr.model_copy(
                    update={
                        "status": "manual_review",
                        "review_reason": reason,
                    }
                )
            evaluations.append(
                _CandidateEvaluation(candidate, candidate_ocr, score, reliable)
            )
        ocr_ms = round((time.perf_counter() - ocr_started) * 1000, 3)
        evaluations.sort(key=lambda item: self._evaluation_key(item), reverse=True)
        selected_eval = evaluations[0]
        reliable_normalized = {
            item.ocr.normalized_text for item in evaluations if item.reliable
        }
        distinct_reliable_plates = len(reliable_normalized) > 1
        ambiguous = (
            not distinct_reliable_plates
            and len(evaluations) > 1
            and selected_eval.reliable
            and evaluations[1].reliable
            and selected_eval.score - evaluations[1].score
            < getattr(settings, "candidate_ambiguity_margin", 0.08)
        )
        if ambiguous or distinct_reliable_plates:
            selected_eval = _CandidateEvaluation(
                selected_eval.candidate,
                selected_eval.ocr.model_copy(
                    update={
                        "status": "manual_review",
                        "review_reason": "MULTIPLE_PLATES_AMBIGUOUS"
                        if distinct_reliable_plates
                        else "PLATE_TEXT_UNRELIABLE",
                    }
                ),
                selected_eval.score,
                False,
            )
        decision = self._decision.decide(selected_eval.ocr)
        return RecognitionAnalysis(
            detection,
            selected_eval.candidate,
            selected_eval.ocr,
            decision,
            detection.total_ms,
            ocr_ms,
        )

    @staticmethod
    def _decode_source_image(image_bytes: bytes) -> np.ndarray | None:
        """Decode the already validated source once for bounded OCR padding."""

        try:
            return cv2.imdecode(
                np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
            )
        except (ValueError, cv2.error):
            return None

    @classmethod
    def _ocr_crop_bytes(
        cls, candidate: object, source_image: np.ndarray | None
    ) -> bytes:
        """Use a bounded padded crop for OCR while preserving the public bbox."""

        if source_image is not None:
            bbox = candidate.bbox
            width = bbox.x2 - bbox.x1
            height = bbox.y2 - bbox.y1
            if width > 0 and height > 0:
                padding_x = int(width * cls._OCR_CROP_PADDING_RATIO)
                padding_y = int(height * cls._OCR_CROP_PADDING_RATIO)
                x1 = max(0, bbox.x1 - padding_x)
                y1 = max(0, bbox.y1 - padding_y)
                x2 = min(source_image.shape[1], bbox.x2 + padding_x)
                y2 = min(source_image.shape[0], bbox.y2 + padding_y)
                padded = source_image[y1:y2, x1:x2]
                success, encoded = cv2.imencode(".png", padded)
                if success:
                    return encoded.tobytes()
        try:
            return base64.b64decode(candidate.crop.base64_data, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise RecognitionOrchestrationError(
                "DETECTION_CROP_INVALID",
                "The detected plate crop could not be processed.",
            ) from exc

    @staticmethod
    def _candidate_order_key(
        candidate: object, detection: ImageDetectionResponse
    ) -> tuple[float, float, int, int, int, int]:
        bbox = candidate.bbox
        return (
            -candidate.confidence,
            -RecognitionOrchestrationService._geometry_score(candidate, detection),
            bbox.x1,
            bbox.y1,
            bbox.x2,
            bbox.y2,
        )

    @staticmethod
    def _geometry_score(candidate: object, detection: ImageDetectionResponse) -> float:
        width = candidate.bbox.x2 - candidate.bbox.x1
        height = candidate.bbox.y2 - candidate.bbox.y1
        if width <= 0 or height <= 0:
            return 0.0
        aspect = width / height
        aspect_score = max(0.0, 1.0 - abs(math.log(max(aspect, 0.01) / 4.0)) / 2.5)
        area_ratio = (
            width * height / max(detection.image_width * detection.image_height, 1)
        )
        area_score = 1.0 if 0.005 <= area_ratio <= 0.35 else 0.5
        return max(0.0, min(1.0, (aspect_score + area_score) / 2.0))

    @staticmethod
    def _candidate_score(
        candidate: object,
        ocr: object,
        grammar_ok: bool,
        detection: ImageDetectionResponse,
    ) -> float:
        ocr_confidence = ocr.confidence if ocr.confidence is not None else 0.0
        mode_score = 1.0 if ocr.mode == "recognition_only" else 0.8
        return (
            0.30 * candidate.confidence
            + 0.35 * ocr_confidence
            + 0.20 * float(grammar_ok)
            + 0.10
            * RecognitionOrchestrationService._geometry_score(candidate, detection)
            + 0.05 * mode_score
        )

    @staticmethod
    def _evaluation_key(
        value: _CandidateEvaluation,
    ) -> tuple[bool, float, float, int, int]:
        bbox = value.candidate.bbox
        return (
            value.reliable,
            value.score,
            value.candidate.confidence,
            -bbox.x1,
            -bbox.y1,
        )
