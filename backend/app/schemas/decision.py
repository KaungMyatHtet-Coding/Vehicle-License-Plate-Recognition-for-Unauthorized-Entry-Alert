"""Schemas for deterministic entry decisions without side effects."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

DecisionStatus = Literal["AUTHORIZED", "UNAUTHORIZED", "MANUAL_REVIEW"]
DecisionReason = Literal[
    "ACTIVE_MATCH",
    "OCR_EMPTY",
    "OCR_LOW_CONFIDENCE",
    "OCR_RESULT_INVALID",
    "DECISION_TIME_INVALID",
    "VEHICLE_NOT_FOUND",
    "VEHICLE_INACTIVE",
    "VEHICLE_BLOCKED",
    "VEHICLE_NOT_YET_VALID",
    "VEHICLE_EXPIRED",
    "VEHICLE_RECORD_INVALID",
    "VEHICLE_LOOKUP_FAILED",
]


class EntryDecision(BaseModel):
    """Auditable decision result that performs no physical or external action."""

    model_config = ConfigDict(extra="forbid")

    correlation_id: str
    decision: DecisionStatus
    reason: DecisionReason
    message: str
    normalized_plate: str
    confidence: float | None
    vehicle_id: UUID | None
    evaluated_at: AwareDatetime
