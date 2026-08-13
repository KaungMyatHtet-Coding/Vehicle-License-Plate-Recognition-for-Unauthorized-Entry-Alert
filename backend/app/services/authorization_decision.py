"""Pure deterministic entry-decision service over OCR and repository contracts."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID

from app.core.config import Settings
from app.repositories.contracts import (
    AuthorizedVehicleRecord,
    AuthorizedVehicleRepository,
)
from app.schemas.decision import DecisionReason, DecisionStatus, EntryDecision
from app.schemas.ocr import PlateOcrResponse

PLATE_PATTERN = re.compile(r"^[A-Z0-9]+$")

DECISION_MESSAGES: dict[DecisionReason, str] = {
    "ACTIVE_MATCH": "The vehicle record permits entry at this time.",
    "OCR_EMPTY": "Plate text could not be read; manual review is required.",
    "OCR_LOW_CONFIDENCE": "Plate text confidence is too low; manual review is required.",
    "OCR_RESULT_INVALID": "The recognition result is invalid; manual review is required.",
    "PLATE_REGION_MISSING": "The plate region could not be confirmed; manual review is required.",
    "PLATE_FORMAT_UNSUPPORTED": "The plate format requires manual review.",
    "PLATE_TEXT_UNRELIABLE": "The detected text is not reliable plate text; manual review is required.",
    "MULTIPLE_PLATES_AMBIGUOUS": "Multiple plate candidates require manual review.",
    "DECISION_TIME_INVALID": "Decision time is unavailable; manual review is required.",
    "VEHICLE_NOT_FOUND": "No matching vehicle record permits entry.",
    "VEHICLE_INACTIVE": "The matching vehicle record is inactive.",
    "VEHICLE_BLOCKED": "The matching vehicle record does not permit entry.",
    "VEHICLE_NOT_YET_VALID": "The matching vehicle record is not yet valid.",
    "VEHICLE_EXPIRED": "The matching vehicle record has expired.",
    "VEHICLE_RECORD_INVALID": "The matching vehicle record is invalid; manual review is required.",
    "VEHICLE_LOOKUP_FAILED": "Vehicle lookup is unavailable; manual review is required.",
}


class AuthorizationDecisionService:
    """Evaluate one Day 8 OCR result without persistence, alerts, or gate control."""

    def __init__(
        self,
        repository: AuthorizedVehicleRepository,
        settings: Settings,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._minimum_confidence = settings.decision_min_confidence
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def decide(self, ocr: PlateOcrResponse) -> EntryDecision:
        """Apply ordered Day 10 rules and fail closed to manual review."""

        evaluated_at = self._safe_now()
        precondition = self._validate_ocr(ocr)
        if precondition is not None:
            decision, reason = precondition
            return self._result(
                ocr,
                decision,
                reason,
                evaluated_at or datetime.min.replace(tzinfo=timezone.utc),
            )
        if evaluated_at is None:
            return self._result(
                ocr,
                "MANUAL_REVIEW",
                "DECISION_TIME_INVALID",
                datetime.min.replace(tzinfo=timezone.utc),
            )

        try:
            record = self._repository.get_by_normalized_plate(ocr.normalized_text)
        except Exception:
            return self._result(
                ocr,
                "MANUAL_REVIEW",
                "VEHICLE_LOOKUP_FAILED",
                evaluated_at,
            )
        if record is None:
            return self._result(ocr, "UNAUTHORIZED", "VEHICLE_NOT_FOUND", evaluated_at)
        if not self._record_is_valid(record, ocr.normalized_text):
            return self._result(
                ocr,
                "MANUAL_REVIEW",
                "VEHICLE_RECORD_INVALID",
                evaluated_at,
            )
        if record.status == "blocked":
            return self._result(
                ocr, "UNAUTHORIZED", "VEHICLE_BLOCKED", evaluated_at, record.id
            )
        if record.status == "inactive":
            return self._result(
                ocr, "UNAUTHORIZED", "VEHICLE_INACTIVE", evaluated_at, record.id
            )
        if record.valid_from is not None and evaluated_at < record.valid_from:
            return self._result(
                ocr,
                "UNAUTHORIZED",
                "VEHICLE_NOT_YET_VALID",
                evaluated_at,
                record.id,
            )
        if record.valid_until is not None and evaluated_at >= record.valid_until:
            return self._result(
                ocr, "UNAUTHORIZED", "VEHICLE_EXPIRED", evaluated_at, record.id
            )
        return self._result(ocr, "AUTHORIZED", "ACTIVE_MATCH", evaluated_at, record.id)

    def _validate_ocr(
        self, ocr: PlateOcrResponse
    ) -> tuple[DecisionStatus, DecisionReason] | None:
        if not isinstance(ocr, PlateOcrResponse):
            return "MANUAL_REVIEW", "OCR_RESULT_INVALID"
        normalized_text = getattr(ocr, "normalized_text", None)
        status = getattr(ocr, "status", None)
        review_reason = getattr(ocr, "review_reason", None)
        confidence = getattr(ocr, "confidence", None)
        if normalized_text == "":
            return "MANUAL_REVIEW", "OCR_EMPTY"
        if not isinstance(normalized_text, str) or not PLATE_PATTERN.fullmatch(
            normalized_text
        ):
            return "MANUAL_REVIEW", "OCR_RESULT_INVALID"
        if (
            confidence is None
            or isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(float(confidence))
            or not 0.0 <= float(confidence) <= 1.0
        ):
            return "MANUAL_REVIEW", "OCR_RESULT_INVALID"
        if status == "manual_review":
            if review_reason in {
                "OCR_LOW_CONFIDENCE",
                "PLATE_REGION_MISSING",
                "PLATE_FORMAT_UNSUPPORTED",
                "PLATE_TEXT_UNRELIABLE",
                "MULTIPLE_PLATES_AMBIGUOUS",
            }:
                return "MANUAL_REVIEW", review_reason
            return "MANUAL_REVIEW", "OCR_RESULT_INVALID"
        if float(confidence) < self._minimum_confidence:
            return "MANUAL_REVIEW", "OCR_LOW_CONFIDENCE"
        if status != "recognized" or review_reason is not None:
            return "MANUAL_REVIEW", "OCR_RESULT_INVALID"
        return None

    @staticmethod
    def _record_is_valid(record: object, normalized_plate: str) -> bool:
        if not isinstance(record, AuthorizedVehicleRecord):
            return False
        timestamps = (
            record.created_at,
            record.updated_at,
            record.valid_from,
            record.valid_until,
        )
        if (
            not isinstance(record.id, UUID)
            or not isinstance(record.normalized_plate, str)
            or record.normalized_plate != normalized_plate
            or not PLATE_PATTERN.fullmatch(record.normalized_plate)
            or record.status not in ("active", "inactive", "blocked")
            or any(
                value is not None
                and (
                    not isinstance(value, datetime)
                    or value.tzinfo is None
                    or value.utcoffset() is None
                )
                for value in timestamps
            )
            or (
                record.valid_from is not None
                and record.valid_until is not None
                and record.valid_until <= record.valid_from
            )
        ):
            return False
        return True

    def _safe_now(self) -> datetime | None:
        try:
            value = self._clock()
        except Exception:
            return None
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            return None
        return value

    @staticmethod
    def _result(
        ocr: PlateOcrResponse,
        decision: DecisionStatus,
        reason: DecisionReason,
        evaluated_at: datetime,
        vehicle_id: UUID | None = None,
    ) -> EntryDecision:
        return EntryDecision(
            correlation_id=AuthorizationDecisionService._safe_string(
                ocr, "correlation_id", uuid_only=True
            ),
            decision=decision,
            reason=reason,
            message=DECISION_MESSAGES[reason],
            normalized_plate=AuthorizationDecisionService._safe_string(
                ocr, "normalized_text"
            ),
            confidence=AuthorizationDecisionService._safe_confidence(ocr),
            vehicle_id=vehicle_id,
            evaluated_at=evaluated_at,
        )

    @staticmethod
    def _safe_confidence(ocr: object) -> float | None:
        value = getattr(ocr, "confidence", None)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0.0 <= float(value) <= 1.0
        ):
            return None
        return float(value)

    @staticmethod
    def _safe_string(value: object, field: str, *, uuid_only: bool = False) -> str:
        result = getattr(value, field, "")
        if not isinstance(result, str):
            return ""
        if uuid_only:
            try:
                return str(UUID(result))
            except (ValueError, AttributeError):
                return ""
        return result
