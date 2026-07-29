"""Immutable Day 11 evidence and detection-logging result contracts."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.schemas.decision import DecisionReason, DecisionStatus, EntryDecision

LoggingFailureCode = Literal[
    "LOG_INPUT_INVALID",
    "LOG_TIME_INVALID",
    "ANNOTATION_FAILED",
    "EVIDENCE_STORAGE_FAILED",
    "EVIDENCE_CONFIRMATION_INVALID",
    "EVIDENCE_ORPHAN_UNVERIFIED",
    "LOG_PERSISTENCE_FAILED",
    "EVIDENCE_CLEANUP_SUCCEEDED",
    "EVIDENCE_CLEANUP_FAILED",
    "SIGNED_ACCESS_FAILED",
]
LoggingStatus = Literal["completed", "partial_failure"]


class EvidenceReference(BaseModel):
    """Private evidence location without a public URL."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bucket: str
    object_path: str


class SignedEvidenceAccess(BaseModel):
    """Opaque short-lived access grant produced by trusted server code."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    token: str
    expires_at: AwareDatetime


class DecisionAuditSnapshot(BaseModel):
    """Frozen value copy of an already-produced Day 10 decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    correlation_id: str
    decision: DecisionStatus
    reason: DecisionReason
    message: str
    normalized_plate: str
    confidence: float | None
    vehicle_id: UUID | None
    evaluated_at: AwareDatetime

    @classmethod
    def from_entry_decision(cls, decision: EntryDecision) -> "DecisionAuditSnapshot":
        """Copy Day 10 values without retaining or mutating its model instance."""

        return cls.model_validate(decision.model_dump())


class DetectionLoggingResult(BaseModel):
    """Outcome that always retains the original authorization decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: DecisionAuditSnapshot
    status: LoggingStatus
    failures: tuple[LoggingFailureCode, ...]
    log_persisted: bool
    evidence: EvidenceReference | None
    signed_access: SignedEvidenceAccess | None
    completed_at: AwareDatetime

    @property
    def has_public_url(self) -> bool:
        """Remain explicit that this contract never returns a public URL."""

        return False
