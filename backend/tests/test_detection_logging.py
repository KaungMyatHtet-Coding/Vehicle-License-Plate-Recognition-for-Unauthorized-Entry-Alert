"""Focused Day 11 tests for private evidence and auditable detection logging."""

from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from uuid import UUID

import cv2
import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError

from app.core.config import Settings
from app.repositories.contracts import RepositoryError
from app.repositories.memory import InMemoryDetectionLogRepository
from app.schemas.decision import EntryDecision
from app.schemas.logging import EvidenceReference
from app.schemas.ocr import PlateOcrResponse
from app.services.detection_logging import DetectionLoggingService
from app.services.evidence_annotation import (
    EvidenceAnnotationError,
    EvidenceAnnotationService,
)
from app.services.evidence_storage import (
    DeletedEvidence,
    EvidenceStorageError,
    InMemoryEvidenceStorage,
    StoredEvidence,
    validate_evidence_location,
)

NOW = datetime(2026, 8, 2, 10, 30, tzinfo=timezone.utc)
CORRELATION_ID = "11111111-1111-4111-8111-111111111111"
VEHICLE_ID = UUID("22222222-2222-4222-8222-222222222222")
PATH_UUID_VALUES = (
    UUID("33333333-3333-4333-8333-333333333333"),
    UUID("44444444-4444-4444-8444-444444444444"),
    UUID("55555555-5555-4555-8555-555555555555"),
    UUID("66666666-6666-4666-8666-666666666666"),
)
SENSITIVE_MARKERS = (
    "fake-secret-value",
    "provider-internal-detail",
    "C:\\private\\evidence.jpg",
    "/srv/private/evidence.jpg",
)


def source_jpeg(*, with_metadata: bool = False) -> bytes:
    image = Image.new("RGB", (160, 80), (235, 235, 235))
    output = io.BytesIO()
    exif = Image.Exif()
    if with_metadata:
        exif[0x010E] = "private source description"
    image.save(output, "JPEG", quality=95, exif=exif)
    return output.getvalue()


def ocr() -> PlateOcrResponse:
    return PlateOcrResponse(
        correlation_id=CORRELATION_ID,
        status="recognized",
        review_reason=None,
        raw_text="YGN 5A-1234",
        normalized_text="YGN5A1234",
        confidence=0.95,
        mode="recognition_only",
        inference_ms=1.0,
        total_ms=2.0,
        image_width=120,
        image_height=32,
    )


def decision() -> EntryDecision:
    return EntryDecision(
        correlation_id=CORRELATION_ID,
        decision="AUTHORIZED",
        reason="ACTIVE_MATCH",
        message="The vehicle record permits entry at this time.",
        normalized_plate="YGN5A1234",
        confidence=0.95,
        vehicle_id=VEHICLE_ID,
        evaluated_at=NOW,
    )


def assert_decision_snapshot(result: object, original: EntryDecision) -> None:
    snapshot = result.decision
    assert snapshot is not original
    assert snapshot.model_dump() == original.model_dump()
    before = original.model_dump()
    with pytest.raises(ValidationError):
        snapshot.message = "attempted mutation"
    assert original.model_dump() == before


def assert_sanitized(value: object) -> None:
    serialized = (
        value.model_dump_json() if hasattr(value, "model_dump_json") else str(value)
    )
    assert all(marker not in serialized for marker in SENSITIVE_MARKERS)


def service(
    logs: object | None = None,
    storage: object | None = None,
    annotation: object | None = None,
) -> tuple[DetectionLoggingService, object, object]:
    log_repository = logs or InMemoryDetectionLogRepository()
    evidence_storage = storage or InMemoryEvidenceStorage(clock=lambda: NOW)
    path_uuids = iter(PATH_UUID_VALUES)
    result = DetectionLoggingService(
        log_repository,
        evidence_storage,
        Settings(),
        annotation_service=annotation,
        clock=lambda: NOW,
        uuid_factory=lambda: next(path_uuids),
    )
    return result, log_repository, evidence_storage


def test_metadata_and_private_evidence_refer_to_exact_same_object() -> None:
    logging, logs, storage = service()
    original_decision = decision()

    result = logging.persist(
        image_bytes=source_jpeg(),
        bbox=(20, 20, 140, 60),
        ocr=ocr(),
        decision=original_decision,
        timings={"total_ms": 12.5, "evidence_ms": 1.25},
    )

    record = logs.get_by_correlation_id(UUID(CORRELATION_ID))
    assert result.status == "completed"
    assert result.log_persisted is True
    assert result.failures == ()
    assert record is not None
    assert record.decision == "AUTHORIZED"
    assert record.decision_reason == "ACTIVE_MATCH"
    assert record.matched_vehicle_id == VEHICLE_ID
    assert (record.evidence_bucket, record.evidence_object_path) == (
        result.evidence.bucket,
        result.evidence.object_path,
    )
    assert storage.get_for_test(result.evidence.bucket, result.evidence.object_path)
    assert result.evidence.bucket == "detection-evidence"
    assert result.signed_access is not None
    assert_decision_snapshot(result, original_decision)
    assert result.has_public_url is False
    assert not hasattr(result, "public_url")


def test_caller_mutation_cannot_change_snapshot_or_persisted_audit() -> None:
    logging, logs, _ = service()
    original = decision()

    result = logging.persist(
        image_bytes=source_jpeg(),
        bbox=(20, 20, 140, 60),
        ocr=ocr(),
        decision=original,
        timings={},
    )
    snapshot_values = result.decision.model_dump()
    record_before = logs.get_by_correlation_id(UUID(CORRELATION_ID))

    original.correlation_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    original.decision = "MANUAL_REVIEW"
    original.reason = "OCR_RESULT_INVALID"
    original.message = "caller-mutated"
    original.normalized_plate = None
    original.confidence = None
    original.vehicle_id = None
    original.evaluated_at = NOW + timedelta(days=1)

    assert result.decision is not original
    assert result.decision.model_dump() == snapshot_values
    with pytest.raises(ValidationError):
        result.decision.reason = "VEHICLE_LOOKUP_FAILED"
    assert logs.get_by_correlation_id(UUID(CORRELATION_ID)) == record_before
    assert record_before is not None
    assert record_before.decision == "AUTHORIZED"
    assert record_before.decision_reason == "ACTIVE_MATCH"
    assert record_before.matched_vehicle_id == VEHICLE_ID


def test_paths_are_unique_relative_and_independent_of_raw_filenames() -> None:
    logging, _, _ = service()
    first = logging._new_object_path(NOW)
    second = logging._new_object_path(NOW)

    assert first != second
    assert first.startswith("2026/08/02/")
    assert first.endswith(".jpg")
    assert not first.startswith("/")
    assert "\\" not in first
    assert ".." not in first.split("/")
    assert "vehicle-upload" not in first
    assert "filename" not in first


@pytest.mark.parametrize(
    ("bucket", "path"),
    [
        ("detection-evidence", "../private.jpg"),
        ("detection-evidence", "/private.jpg"),
        ("detection-evidence", "safe\\private.jpg"),
        ("Detection Evidence", "safe/private.jpg"),
        ("detection-evidence", "C:/private.jpg"),
    ],
)
def test_storage_rejects_traversal_and_unsafe_locations(bucket: str, path: str) -> None:
    with pytest.raises(EvidenceStorageError) as caught:
        validate_evidence_location(bucket, path)
    assert caught.value.code == "EVIDENCE_LOCATION_INVALID"


def test_annotation_is_deterministic_non_mutating_and_strips_metadata() -> None:
    source = source_jpeg(with_metadata=True)
    original = bytes(source)
    annotation = EvidenceAnnotationService()

    first = annotation.annotate(source, (20, 20, 140, 60), decision())
    second = annotation.annotate(source, (20, 20, 140, 60), decision())

    assert first == second
    assert source == original
    with Image.open(io.BytesIO(first)) as image:
        assert image.format == "JPEG"
        assert image.getexif() == {}
        assert image.size == (160, 80)
    decoded = cv2.imdecode(np.frombuffer(first, np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None


@pytest.mark.parametrize(
    "bbox",
    [
        (-1, 0, 10, 10),
        (0, 0, 161, 10),
        (10, 10, 10, 20),
        (10, 10, 20, 10),
        (True, 0, 10, 10),
        (0, 0, 10, 10.5),
    ],
)
def test_annotation_rejects_invalid_bounding_boxes(bbox: object) -> None:
    with pytest.raises(EvidenceAnnotationError) as caught:
        EvidenceAnnotationService().annotate(source_jpeg(), bbox, decision())
    assert caught.value.code == "EVIDENCE_BBOX_INVALID"


class FailedAnnotation:
    def annotate(self, *_: object) -> bytes:
        raise RuntimeError(" | ".join(SENSITIVE_MARKERS))


class FailedStorage(InMemoryEvidenceStorage):
    def store(self, *_: object) -> object:
        raise RuntimeError(" | ".join(SENSITIVE_MARKERS))


class ConfirmationMismatchStorage(InMemoryEvidenceStorage):
    def __init__(self, mismatch: str) -> None:
        super().__init__(clock=lambda: NOW)
        self.mismatch = mismatch

    def store(
        self, bucket: str, object_path: str, content: bytes, content_type: str
    ) -> StoredEvidence:
        stored = super().store(bucket, object_path, content, content_type)
        if self.mismatch == "bucket":
            return replace(
                stored,
                reference=stored.reference.model_copy(
                    update={"bucket": "different-private-bucket"}
                ),
            )
        if self.mismatch == "path":
            return replace(
                stored,
                reference=stored.reference.model_copy(
                    update={"object_path": "different/object.jpg"}
                ),
            )
        if self.mismatch == "sensitive":
            return replace(
                stored,
                reference=stored.reference.model_copy(
                    update={"object_path": "C:\\private\\evidence.jpg"}
                ),
            )
        return replace(stored, sha256="0" * 64)


class UnrelatedClaimStorage(InMemoryEvidenceStorage):
    def __init__(self, unrelated: EvidenceReference) -> None:
        super().__init__(clock=lambda: NOW)
        self.unrelated = unrelated

    def store(
        self, bucket: str, object_path: str, content: bytes, content_type: str
    ) -> StoredEvidence:
        stored = super().store(bucket, object_path, content, content_type)
        return replace(stored, reference=self.unrelated)


class SensitiveClaimStorage(InMemoryEvidenceStorage):
    def __init__(self, marker: str) -> None:
        super().__init__(clock=lambda: NOW)
        self.marker = marker

    def store(
        self, bucket: str, object_path: str, content: bytes, content_type: str
    ) -> StoredEvidence:
        stored = super().store(bucket, object_path, content, content_type)
        return replace(
            stored,
            reference=stored.reference.model_copy(
                update={"object_path": f"claimed/{self.marker}"}
            ),
        )


class FailedLogs:
    def add(self, _: object) -> None:
        raise RepositoryError("PRIVATE_DATABASE_ERROR", " | ".join(SENSITIVE_MARKERS))


class FailedDeleteStorage(InMemoryEvidenceStorage):
    def delete(self, *_: object) -> None:
        raise RuntimeError(" | ".join(SENSITIVE_MARKERS))


class NoOpDeleteStorage(InMemoryEvidenceStorage):
    def delete(self, *_: object) -> object:
        """Return no authoritative confirmation and deliberately retain the object."""

        return None


class DishonestExactDeleteStorage(InMemoryEvidenceStorage):
    def delete(self, bucket: str, object_path: str) -> DeletedEvidence:
        return DeletedEvidence(
            reference=EvidenceReference(bucket=bucket, object_path=object_path)
        )


class MismatchedDeleteStorage(InMemoryEvidenceStorage):
    def delete(self, bucket: str, object_path: str) -> DeletedEvidence:
        return DeletedEvidence(
            reference=EvidenceReference(
                bucket=bucket, object_path=f"{object_path}.different"
            )
        )


class VerificationErrorStorage(InMemoryEvidenceStorage):
    def exists(self, *_: object) -> bool:
        raise RuntimeError(" | ".join(SENSITIVE_MARKERS))


class DishonestPresentStorage(InMemoryEvidenceStorage):
    def delete(self, bucket: str, object_path: str) -> DeletedEvidence:
        deleted = super().delete(bucket, object_path)
        return deleted

    def exists(self, *_: object) -> bool:
        return True


class FailedSigningStorage(InMemoryEvidenceStorage):
    def create_signed_access(self, *_: object) -> object:
        raise RuntimeError(" | ".join(SENSITIVE_MARKERS))


@pytest.mark.parametrize("mismatch", ["bucket", "path", "sensitive", "digest"])
def test_storage_confirmation_mismatch_never_creates_false_association(
    mismatch: str,
) -> None:
    storage = ConfirmationMismatchStorage(mismatch)
    logging, logs, _ = service(storage=storage)
    original_decision = decision()

    result = logging.persist(
        image_bytes=source_jpeg(),
        bbox=(20, 20, 140, 60),
        ocr=ocr(),
        decision=original_decision,
        timings={},
    )

    record = logs.get_by_correlation_id(UUID(CORRELATION_ID))
    assert_decision_snapshot(result, original_decision)
    assert result.failures[0] == "EVIDENCE_CONFIRMATION_INVALID"
    cleanup_index = 2 if mismatch in ("bucket", "path", "sensitive") else 1
    if cleanup_index == 2:
        assert result.failures[1] == "EVIDENCE_ORPHAN_UNVERIFIED"
    assert result.failures[cleanup_index] in (
        "EVIDENCE_CLEANUP_SUCCEEDED",
        "EVIDENCE_CLEANUP_FAILED",
    )
    assert result.log_persisted is True
    assert result.evidence is None
    assert result.signed_access is None
    assert record is not None
    assert record.evidence_bucket is None
    assert record.evidence_object_path is None
    requested_path = (
        "2026/08/02/33333333-3333-4333-8333-333333333333/"
        "44444444-4444-4444-8444-444444444444.jpg"
    )
    assert storage.get_for_test("detection-evidence", requested_path) is None
    assert_sanitized(result)


def test_untrusted_claim_cannot_delete_unrelated_existing_evidence() -> None:
    unrelated = EvidenceReference(
        bucket="detection-evidence",
        object_path="2026/08/01/unrelated-existing.jpg",
    )
    unrelated_bytes = b"unrelated-valid-evidence"
    storage = UnrelatedClaimStorage(unrelated)
    storage.store(
        unrelated.bucket, unrelated.object_path, unrelated_bytes, "image/jpeg"
    )
    logging, logs, _ = service(storage=storage)

    result = logging.persist(
        image_bytes=source_jpeg(),
        bbox=(20, 20, 140, 60),
        ocr=ocr(),
        decision=decision(),
        timings={},
    )

    assert result.failures == (
        "EVIDENCE_CONFIRMATION_INVALID",
        "EVIDENCE_ORPHAN_UNVERIFIED",
        "EVIDENCE_CLEANUP_SUCCEEDED",
    )
    assert storage.get_for_test(unrelated.bucket, unrelated.object_path) == (
        unrelated_bytes
    )
    assert unrelated.object_path not in result.model_dump_json()
    assert result.evidence is None
    record = logs.get_by_correlation_id(UUID(CORRELATION_ID))
    assert record is not None
    assert record.evidence_bucket is None
    assert record.evidence_object_path is None


@pytest.mark.parametrize("marker", SENSITIVE_MARKERS)
def test_confirmation_mismatch_never_exposes_sensitive_claim(marker: str) -> None:
    storage = SensitiveClaimStorage(marker)
    logging, logs, _ = service(storage=storage)

    result = logging.persist(
        image_bytes=source_jpeg(),
        bbox=(20, 20, 140, 60),
        ocr=ocr(),
        decision=decision(),
        timings={},
    )

    assert "EVIDENCE_CONFIRMATION_INVALID" in result.failures
    assert "EVIDENCE_ORPHAN_UNVERIFIED" in result.failures
    assert marker not in result.model_dump_json()
    assert_sanitized(result)
    record = logs.get_by_correlation_id(UUID(CORRELATION_ID))
    assert record is not None
    assert marker not in str(record)
    assert record.evidence_bucket is None
    assert record.evidence_object_path is None


@pytest.mark.parametrize(
    ("annotation", "storage", "failure"),
    [
        (FailedAnnotation(), None, "ANNOTATION_FAILED"),
        (None, FailedStorage(), "EVIDENCE_STORAGE_FAILED"),
    ],
)
def test_evidence_failure_retains_metadata_log_and_original_decision(
    annotation: object | None,
    storage: object | None,
    failure: str,
) -> None:
    logging, logs, _ = service(storage=storage, annotation=annotation)
    original_decision = decision()

    result = logging.persist(
        image_bytes=source_jpeg(),
        bbox=(20, 20, 140, 60),
        ocr=ocr(),
        decision=original_decision,
        timings={"total_ms": 2.0},
    )

    record = logs.get_by_correlation_id(UUID(CORRELATION_ID))
    assert_decision_snapshot(result, original_decision)
    assert result.decision.decision == "AUTHORIZED"
    assert result.failures == (failure,)
    assert result.log_persisted is True
    assert result.evidence is None
    assert record is not None
    assert record.evidence_bucket is None
    assert record.decision == original_decision.decision
    assert_sanitized(result)


def test_log_failure_cleans_up_stored_evidence_and_preserves_decision() -> None:
    storage = InMemoryEvidenceStorage(clock=lambda: NOW)
    logging, _, _ = service(logs=FailedLogs(), storage=storage)
    original_decision = decision()

    result = logging.persist(
        image_bytes=source_jpeg(),
        bbox=(20, 20, 140, 60),
        ocr=ocr(),
        decision=original_decision,
        timings={},
    )

    assert_decision_snapshot(result, original_decision)
    assert result.failures == (
        "LOG_PERSISTENCE_FAILED",
        "EVIDENCE_CLEANUP_SUCCEEDED",
    )
    assert result.log_persisted is False
    assert result.evidence is None
    assert_sanitized(result)
    requested_path = (
        "2026/08/02/33333333-3333-4333-8333-333333333333/"
        "44444444-4444-4444-8444-444444444444.jpg"
    )
    assert storage.get_for_test("detection-evidence", requested_path) is None


def test_cleanup_failure_is_visible_without_changing_decision() -> None:
    storage = FailedDeleteStorage()
    logging, _, _ = service(logs=FailedLogs(), storage=storage)

    original_decision = decision()
    result = logging.persist(
        image_bytes=source_jpeg(),
        bbox=(20, 20, 140, 60),
        ocr=ocr(),
        decision=original_decision,
        timings={},
    )

    assert result.decision.decision == "AUTHORIZED"
    assert_decision_snapshot(result, original_decision)
    assert result.failures == (
        "LOG_PERSISTENCE_FAILED",
        "EVIDENCE_CLEANUP_FAILED",
    )
    assert result.evidence is not None
    assert storage.get_for_test(result.evidence.bucket, result.evidence.object_path)
    assert_sanitized(result)


def test_no_op_cleanup_without_confirmation_is_never_reported_successful() -> None:
    storage = NoOpDeleteStorage(clock=lambda: NOW)
    logging, _, _ = service(logs=FailedLogs(), storage=storage)
    original_decision = decision()

    result = logging.persist(
        image_bytes=source_jpeg(),
        bbox=(20, 20, 140, 60),
        ocr=ocr(),
        decision=original_decision,
        timings={},
    )

    assert result.failures == (
        "LOG_PERSISTENCE_FAILED",
        "EVIDENCE_CLEANUP_FAILED",
    )
    assert result.evidence is not None
    assert_decision_snapshot(result, original_decision)
    assert (
        storage.get_for_test(result.evidence.bucket, result.evidence.object_path)
        is not None
    )


@pytest.mark.parametrize(
    "storage",
    [
        DishonestExactDeleteStorage(clock=lambda: NOW),
        MismatchedDeleteStorage(clock=lambda: NOW),
        NoOpDeleteStorage(clock=lambda: NOW),
        VerificationErrorStorage(clock=lambda: NOW),
        DishonestPresentStorage(clock=lambda: NOW),
    ],
)
def test_cleanup_requires_matching_confirmation_and_verified_absence(
    storage: InMemoryEvidenceStorage,
) -> None:
    logging, _, _ = service(logs=FailedLogs(), storage=storage)
    original_decision = decision()

    result = logging.persist(
        image_bytes=source_jpeg(),
        bbox=(20, 20, 140, 60),
        ocr=ocr(),
        decision=original_decision,
        timings={},
    )

    assert result.failures == (
        "LOG_PERSISTENCE_FAILED",
        "EVIDENCE_CLEANUP_FAILED",
    )
    assert "EVIDENCE_CLEANUP_SUCCEEDED" not in result.failures
    assert result.evidence is not None
    assert_decision_snapshot(result, original_decision)
    assert_sanitized(result)


def test_exact_but_dishonest_delete_retains_object_and_orphan_reference() -> None:
    storage = DishonestExactDeleteStorage(clock=lambda: NOW)
    logging, _, _ = service(logs=FailedLogs(), storage=storage)
    original_decision = decision()

    result = logging.persist(
        image_bytes=source_jpeg(),
        bbox=(20, 20, 140, 60),
        ocr=ocr(),
        decision=original_decision,
        timings={},
    )

    assert result.failures[-1] == "EVIDENCE_CLEANUP_FAILED"
    assert result.evidence is not None
    assert storage.exists(result.evidence.bucket, result.evidence.object_path) is True
    assert (
        storage.get_for_test(result.evidence.bucket, result.evidence.object_path)
        is not None
    )
    assert_decision_snapshot(result, original_decision)


def test_signed_access_failure_is_visible_after_log_and_storage_succeed() -> None:
    storage = FailedSigningStorage()
    logging, logs, _ = service(storage=storage)

    original_decision = decision()
    result = logging.persist(
        image_bytes=source_jpeg(),
        bbox=(20, 20, 140, 60),
        ocr=ocr(),
        decision=original_decision,
        timings={},
    )

    assert result.failures == ("SIGNED_ACCESS_FAILED",)
    assert_decision_snapshot(result, original_decision)
    assert result.log_persisted is True
    assert result.evidence is not None
    assert result.signed_access is None
    record = logs.get_by_correlation_id(UUID(CORRELATION_ID))
    assert record is not None
    assert (record.evidence_bucket, record.evidence_object_path) == (
        result.evidence.bucket,
        result.evidence.object_path,
    )
    assert (
        storage.get_for_test(result.evidence.bucket, result.evidence.object_path)
        is not None
    )
    assert_sanitized(result)


def test_signed_access_and_retention_settings_have_safe_bounds() -> None:
    settings = Settings()
    assert settings.evidence_storage_bucket == "detection-evidence"
    assert settings.evidence_signed_access_ttl_seconds == 300
    assert settings.evidence_retention_days == 30

    for value in (59, 3601, True):
        with pytest.raises(ValidationError):
            Settings(EVIDENCE_SIGNED_ACCESS_TTL_SECONDS=value)
    for value in (0, 366, True):
        with pytest.raises(ValidationError):
            Settings(EVIDENCE_RETENTION_DAYS=value)
    with pytest.raises(ValidationError):
        Settings(EVIDENCE_STORAGE_BUCKET="../public")

    current = [NOW]
    storage = InMemoryEvidenceStorage(clock=lambda: current[0])
    storage.store(
        "detection-evidence",
        "2026/08/02/signed.jpg",
        b"jpeg",
        "image/jpeg",
    )
    for value in (59, 3601, True):
        with pytest.raises(EvidenceStorageError) as caught:
            storage.create_signed_access(
                "detection-evidence", "2026/08/02/signed.jpg", value
            )
        assert caught.value.code == "EVIDENCE_SIGNED_LIFETIME_INVALID"

    minimum = storage.create_signed_access(
        "detection-evidence", "2026/08/02/signed.jpg", 60
    )
    maximum = storage.create_signed_access(
        "detection-evidence", "2026/08/02/signed.jpg", 3600
    )
    default = storage.create_signed_access(
        "detection-evidence", "2026/08/02/signed.jpg", 300
    )
    assert minimum.expires_at == NOW + timedelta(seconds=60)
    assert maximum.expires_at == NOW + timedelta(seconds=3600)
    assert default.expires_at == NOW + timedelta(seconds=300)
    assert len({minimum.token, maximum.token, default.token}) == 3
    for grant in (minimum, maximum, default):
        assert storage.resolve_signed_access(grant.token) == b"jpeg"
        assert "detection-evidence" not in grant.token
        assert "signed.jpg" not in grant.token
        assert "http" not in grant.token.lower()
        assert "supabase" not in grant.token.lower()


def test_signed_grant_is_object_bound_expires_and_is_revoked_on_delete() -> None:
    current = [NOW]
    storage = InMemoryEvidenceStorage(clock=lambda: current[0])
    storage.store("detection-evidence", "first.jpg", b"first", "image/jpeg")
    storage.store("detection-evidence", "second.jpg", b"second", "image/jpeg")
    first_grant = storage.create_signed_access("detection-evidence", "first.jpg", 300)
    second_grant = storage.create_signed_access("detection-evidence", "second.jpg", 300)

    assert storage.resolve_signed_access(first_grant.token) == b"first"
    assert storage.resolve_signed_access(second_grant.token) == b"second"
    deleted = storage.delete("detection-evidence", "first.jpg")
    assert deleted.reference.object_path == "first.jpg"
    with pytest.raises(EvidenceStorageError) as deleted_grant:
        storage.resolve_signed_access(first_grant.token)
    assert deleted_grant.value.code == "EVIDENCE_GRANT_INVALID"
    assert storage.resolve_signed_access(second_grant.token) == b"second"

    current[0] = NOW + timedelta(seconds=300)
    with pytest.raises(EvidenceStorageError) as expired:
        storage.resolve_signed_access(second_grant.token)
    assert expired.value.code == "EVIDENCE_GRANT_EXPIRED"
    with pytest.raises(EvidenceStorageError) as unknown:
        storage.resolve_signed_access("unknown-private-token")
    assert unknown.value.code == "EVIDENCE_GRANT_INVALID"


def test_signed_grant_resolution_errors_are_sanitized() -> None:
    fail_clock = [False]

    def clock() -> datetime:
        if fail_clock[0]:
            raise RuntimeError(" | ".join(SENSITIVE_MARKERS))
        return NOW

    storage = InMemoryEvidenceStorage(clock=clock)
    storage.store("detection-evidence", "private.jpg", b"private", "image/jpeg")
    grant = storage.create_signed_access("detection-evidence", "private.jpg", 300)
    fail_clock[0] = True

    with pytest.raises(EvidenceStorageError) as failed:
        storage.resolve_signed_access(grant.token)

    assert failed.value.code == "EVIDENCE_TIME_INVALID"
    assert_sanitized(failed.value)


def test_mismatched_audit_inputs_fail_safely_before_any_persistence() -> None:
    logging, logs, storage = service()
    mismatched = decision().model_copy(update={"normalized_plate": "OTHER123"})

    result = logging.persist(
        image_bytes=source_jpeg(),
        bbox=(20, 20, 140, 60),
        ocr=ocr(),
        decision=mismatched,
        timings={},
    )

    assert_decision_snapshot(result, mismatched)
    assert result.failures == ("LOG_INPUT_INVALID",)
    assert result.log_persisted is False
    assert result.evidence is None
    assert logs.get_by_correlation_id(UUID(CORRELATION_ID)) is None
    assert (
        storage.get_for_test(
            "detection-evidence",
            "2026/08/02/33333333-3333-4333-8333-333333333333/"
            "44444444-4444-4444-8444-444444444444.jpg",
        )
        is None
    )


@pytest.mark.parametrize(
    "clock",
    [
        lambda: datetime(2026, 8, 2),
        lambda: (_ for _ in ()).throw(RuntimeError(" | ".join(SENSITIVE_MARKERS))),
    ],
)
def test_invalid_logging_clock_is_visible_and_preserves_decision(
    clock: object,
) -> None:
    logs = InMemoryDetectionLogRepository()
    storage = InMemoryEvidenceStorage(clock=lambda: NOW)
    logging = DetectionLoggingService(
        logs,
        storage,
        Settings(),
        clock=clock,
    )
    original = decision()

    result = logging.persist(
        image_bytes=source_jpeg(),
        bbox=(20, 20, 140, 60),
        ocr=ocr(),
        decision=original,
        timings={},
    )

    assert_decision_snapshot(result, original)
    assert result.failures == ("LOG_TIME_INVALID",)
    assert result.log_persisted is False
    assert result.evidence is None
    assert_sanitized(result)


def test_path_generation_failure_is_sanitized_as_storage_failure() -> None:
    logging, logs, _ = service()
    logging._uuid_factory = lambda: (_ for _ in ()).throw(
        RuntimeError("private path generator details")
    )

    original_decision = decision()
    result = logging.persist(
        image_bytes=source_jpeg(),
        bbox=(20, 20, 140, 60),
        ocr=ocr(),
        decision=original_decision,
        timings={},
    )

    assert result.decision.decision == "AUTHORIZED"
    assert_decision_snapshot(result, original_decision)
    assert result.failures == ("EVIDENCE_STORAGE_FAILED",)
    assert result.log_persisted is True
    assert result.evidence is None
    assert logs.get_by_correlation_id(UUID(CORRELATION_ID)) is not None
    assert "private path" not in result.model_dump_json()


def test_storage_import_and_use_perform_no_network_or_filesystem_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_: object, **__: object) -> None:
        raise AssertionError("external I/O attempted")

    monkeypatch.setattr("socket.create_connection", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    storage = InMemoryEvidenceStorage()

    stored = storage.store(
        "detection-evidence", "2026/08/02/object.jpg", b"jpeg", "image/jpeg"
    )

    assert stored.byte_count == 4
    assert (
        storage.get_for_test(stored.reference.bucket, stored.reference.object_path)
        == b"jpeg"
    )


def test_concurrent_duplicate_store_is_atomic_and_reads_are_defensive() -> None:
    storage = InMemoryEvidenceStorage(clock=lambda: NOW)
    bucket = "detection-evidence"
    path = "2026/08/02/concurrent.jpg"

    def store_once(_: int) -> str:
        try:
            storage.store(bucket, path, b"immutable-evidence", "image/jpeg")
        except EvidenceStorageError as error:
            return error.code
        return "STORED"

    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(executor.map(store_once, range(16)))
        reads = list(
            executor.map(
                lambda _: storage.get_for_test(bucket, path),
                range(32),
            )
        )

    assert outcomes.count("STORED") == 1
    assert outcomes.count("EVIDENCE_OBJECT_EXISTS") == 15
    assert all(value == b"immutable-evidence" for value in reads)
    assert len({id(value) for value in reads}) > 1
    assert storage.get_for_test(bucket, path) == b"immutable-evidence"


def test_concurrent_sign_resolve_and_delete_interaction_fails_safely() -> None:
    storage = InMemoryEvidenceStorage(clock=lambda: NOW)
    bucket = "detection-evidence"
    path = "2026/08/02/race.jpg"
    storage.store(bucket, path, b"race-evidence", "image/jpeg")
    initial_grant = storage.create_signed_access(bucket, path, 300)
    barrier = Barrier(3)

    def resolve_once() -> bytes | str:
        barrier.wait()
        try:
            return storage.resolve_signed_access(initial_grant.token)
        except EvidenceStorageError as error:
            return error.code

    def sign_once() -> object:
        barrier.wait()
        try:
            return storage.create_signed_access(bucket, path, 300)
        except EvidenceStorageError as error:
            return error.code

    def delete_once() -> str:
        barrier.wait()
        return storage.delete(bucket, path).reference.object_path

    with ThreadPoolExecutor(max_workers=3) as executor:
        resolved_future = executor.submit(resolve_once)
        signed_future = executor.submit(sign_once)
        deleted_future = executor.submit(delete_once)
        resolved = resolved_future.result(timeout=5)
        signed = signed_future.result(timeout=5)
        deleted = deleted_future.result(timeout=5)

    assert resolved in (b"race-evidence", "EVIDENCE_GRANT_INVALID")
    assert getattr(signed, "token", signed) != initial_grant.token
    assert signed == "EVIDENCE_OBJECT_MISSING" or hasattr(signed, "token")
    assert deleted == path
    with pytest.raises(EvidenceStorageError) as revoked:
        storage.resolve_signed_access(initial_grant.token)
    assert revoked.value.code == "EVIDENCE_GRANT_INVALID"
    if hasattr(signed, "token"):
        with pytest.raises(EvidenceStorageError) as concurrently_revoked:
            storage.resolve_signed_access(signed.token)
        assert concurrently_revoked.value.code == "EVIDENCE_GRANT_INVALID"
    assert storage.get_for_test(bucket, path) is None
    assert storage.exists(bucket, path) is False
