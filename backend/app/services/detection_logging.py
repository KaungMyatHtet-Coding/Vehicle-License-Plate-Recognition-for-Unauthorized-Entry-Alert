"""Day 11 orchestration for auditable logs and private evidence."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.core.config import Settings
from app.repositories.contracts import DetectionLogRecord, DetectionLogRepository
from app.schemas.decision import EntryDecision
from app.schemas.logging import (
    DecisionAuditSnapshot,
    DetectionLoggingResult,
    EvidenceReference,
    LoggingFailureCode,
    SignedEvidenceAccess,
)
from app.schemas.ocr import PlateOcrResponse
from app.services.evidence_annotation import EvidenceAnnotationService
from app.services.evidence_storage import (
    DeletedEvidence,
    EvidenceStorage,
    StoredEvidence,
)


class DetectionLoggingService:
    """Persist metadata/evidence without ever recalculating the supplied decision."""

    def __init__(
        self,
        log_repository: DetectionLogRepository,
        evidence_storage: EvidenceStorage,
        settings: Settings,
        *,
        annotation_service: EvidenceAnnotationService | None = None,
        clock: Callable[[], datetime] | None = None,
        uuid_factory: Callable[[], UUID] | None = None,
    ) -> None:
        self._logs = log_repository
        self._storage = evidence_storage
        self._bucket = settings.evidence_storage_bucket
        self._signed_lifetime = settings.evidence_signed_access_ttl_seconds
        self._annotation = annotation_service or EvidenceAnnotationService()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._uuid_factory = uuid_factory or uuid4

    def persist(
        self,
        *,
        image_bytes: bytes,
        bbox: tuple[int, int, int, int],
        ocr: PlateOcrResponse,
        decision: EntryDecision,
        timings: dict[str, float],
    ) -> DetectionLoggingResult:
        """Store evidence and metadata with explicit compensating-failure results."""

        snapshot = DecisionAuditSnapshot.from_entry_decision(decision)
        completed_at = self._safe_now()
        failures: list[LoggingFailureCode] = []
        reference: EvidenceReference | None = None
        signed_access = None
        if completed_at is None:
            return self._result(
                snapshot,
                ["LOG_TIME_INVALID"],
                False,
                None,
                None,
                datetime.min.replace(tzinfo=timezone.utc),
            )
        if not self._inputs_are_associable(ocr, snapshot):
            return self._result(
                snapshot,
                ["LOG_INPUT_INVALID"],
                False,
                None,
                None,
                completed_at,
            )

        try:
            evidence_bytes = self._annotation.annotate(image_bytes, bbox, snapshot)
        except Exception:
            failures.append("ANNOTATION_FAILED")
        else:
            requested_reference: EvidenceReference | None = None
            try:
                requested_reference = EvidenceReference(
                    bucket=self._bucket,
                    object_path=self._new_object_path(completed_at),
                )
                stored = self._storage.store(
                    requested_reference.bucket,
                    requested_reference.object_path,
                    evidence_bytes,
                    "image/jpeg",
                )
                if not self._storage_confirmation_matches(
                    stored, requested_reference, evidence_bytes
                ):
                    failures.append("EVIDENCE_CONFIRMATION_INVALID")
                    if (
                        isinstance(stored, StoredEvidence)
                        and stored.reference != requested_reference
                    ):
                        failures.append("EVIDENCE_ORPHAN_UNVERIFIED")
                    if self._delete_confirmed(requested_reference):
                        failures.append("EVIDENCE_CLEANUP_SUCCEEDED")
                    else:
                        failures.append("EVIDENCE_CLEANUP_FAILED")
                else:
                    reference = stored.reference
            except Exception:
                failures.append("EVIDENCE_STORAGE_FAILED")
                reference = None

        try:
            record = self._build_record(ocr, snapshot, timings, completed_at, reference)
            self._logs.add(record)
        except Exception:
            failures.append("LOG_PERSISTENCE_FAILED")
            if reference is not None:
                if self._delete_confirmed(reference):
                    failures.append("EVIDENCE_CLEANUP_SUCCEEDED")
                    reference = None
                else:
                    failures.append("EVIDENCE_CLEANUP_FAILED")
            return self._result(
                snapshot, failures, False, reference, None, completed_at
            )

        if reference is not None:
            try:
                signed_access = self._storage.create_signed_access(
                    reference.bucket,
                    reference.object_path,
                    self._signed_lifetime,
                )
            except Exception:
                failures.append("SIGNED_ACCESS_FAILED")

        return self._result(
            snapshot, failures, True, reference, signed_access, completed_at
        )

    def _new_object_path(self, timestamp: datetime) -> str:
        return f"{timestamp:%Y/%m/%d}/{self._uuid_factory()}/{self._uuid_factory()}.jpg"

    @staticmethod
    def _inputs_are_associable(
        ocr: PlateOcrResponse, decision: DecisionAuditSnapshot
    ) -> bool:
        try:
            correlation_id = UUID(decision.correlation_id)
        except (ValueError, TypeError, AttributeError):
            return False
        return (
            isinstance(ocr, PlateOcrResponse)
            and isinstance(decision, DecisionAuditSnapshot)
            and ocr.correlation_id == str(correlation_id)
            and decision.normalized_plate == ocr.normalized_text
            and decision.confidence == ocr.confidence
        )

    @staticmethod
    def _build_record(
        ocr: PlateOcrResponse,
        decision: DecisionAuditSnapshot,
        timings: dict[str, float],
        created_at: datetime,
        evidence: EvidenceReference | None,
    ) -> DetectionLogRecord:
        return DetectionLogRecord(
            id=uuid4(),
            correlation_id=UUID(decision.correlation_id),
            raw_text=ocr.raw_text,
            normalized_text=ocr.normalized_text,
            confidence=ocr.confidence,
            ocr_status=ocr.status,
            review_reason=ocr.review_reason,
            decision=decision.decision,
            decision_reason=decision.reason,
            matched_vehicle_id=decision.vehicle_id,
            evidence_bucket=evidence.bucket if evidence else None,
            evidence_object_path=evidence.object_path if evidence else None,
            timings=dict(timings),
            created_at=created_at,
        )

    @staticmethod
    def _result(
        decision: DecisionAuditSnapshot,
        failures: list[LoggingFailureCode],
        log_persisted: bool,
        evidence: EvidenceReference | None,
        signed_access: SignedEvidenceAccess | None,
        completed_at: datetime,
    ) -> DetectionLoggingResult:
        return DetectionLoggingResult(
            decision=decision,
            status="partial_failure" if failures else "completed",
            failures=tuple(failures),
            log_persisted=log_persisted,
            evidence=evidence,
            signed_access=signed_access,
            completed_at=completed_at,
        )

    @staticmethod
    def _storage_confirmation_matches(
        stored: object,
        requested: EvidenceReference,
        content: bytes,
    ) -> bool:
        return (
            isinstance(stored, StoredEvidence)
            and stored.reference == requested
            and stored.byte_count == len(content)
            and stored.sha256 == hashlib.sha256(content).hexdigest()
        )

    def _delete_confirmed(self, reference: EvidenceReference) -> bool:
        try:
            deleted = self._storage.delete(reference.bucket, reference.object_path)
        except Exception:
            return False
        if not isinstance(deleted, DeletedEvidence) or deleted.reference != reference:
            return False
        try:
            exists = self._storage.exists(reference.bucket, reference.object_path)
        except Exception:
            return False
        return isinstance(exists, bool) and not exists

    def _safe_now(self) -> datetime | None:
        try:
            value = self._clock()
        except Exception:
            value = None
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            return None
        return value
