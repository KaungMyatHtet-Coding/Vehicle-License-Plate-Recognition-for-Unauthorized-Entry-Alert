"""Focused Day 9 tests for schema and network-free repository contracts."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from app.repositories.contracts import (
    AuthorizedVehicleRecord,
    DetectionLogRecord,
    RepositoryError,
    SettingRecord,
)
from app.repositories.memory import (
    InMemoryAuthorizedVehicleRepository,
    InMemoryDetectionLogRepository,
    InMemorySettingsRepository,
    utc_now,
)


def vehicle(**changes: object) -> AuthorizedVehicleRecord:
    now = utc_now()
    record = AuthorizedVehicleRecord(
        id=uuid4(),
        normalized_plate="YGN5A1234",
        status="active",
        valid_from=now,
        valid_until=now + timedelta(days=30),
        created_at=now,
        updated_at=now,
        description=None,
    )
    return replace(record, **changes)


def detection(**changes: object) -> DetectionLogRecord:
    record = DetectionLogRecord(
        id=uuid4(),
        correlation_id=uuid4(),
        raw_text="YGN 5A-1234",
        normalized_text="YGN5A1234",
        confidence=0.95,
        ocr_status="recognized",
        review_reason=None,
        evidence_bucket=None,
        evidence_object_path=None,
        timings={"ocr_ms": 12.5},
        created_at=utc_now(),
    )
    return replace(record, **changes)


def test_authorized_vehicle_lookup_uses_exact_normalized_uniqueness() -> None:
    repository = InMemoryAuthorizedVehicleRepository()
    record = vehicle()

    repository.add(record)

    assert repository.get_by_normalized_plate("YGN5A1234") == record
    with pytest.raises(RepositoryError) as caught:
        repository.add(vehicle(id=uuid4()))
    assert caught.value.code == "REPOSITORY_PLATE_DUPLICATE"


@pytest.mark.parametrize("plate", ["ygn5a1234", "YGN 5A1234", "", "YGN-5A1234"])
def test_vehicle_repository_rejects_non_normalized_plate(plate: str) -> None:
    repository = InMemoryAuthorizedVehicleRepository()

    with pytest.raises(RepositoryError) as caught:
        repository.add(vehicle(normalized_plate=plate))

    assert caught.value.code == "REPOSITORY_PLATE_INVALID"


def test_vehicle_repository_validates_status_dates_and_timezone() -> None:
    repository = InMemoryAuthorizedVehicleRepository()
    now = utc_now()

    with pytest.raises(RepositoryError) as status_error:
        repository.add(vehicle(status="unknown"))
    assert status_error.value.code == "REPOSITORY_STATUS_INVALID"
    with pytest.raises(RepositoryError) as validity_error:
        repository.add(vehicle(valid_from=now, valid_until=now))
    assert validity_error.value.code == "REPOSITORY_VALIDITY_INVALID"
    with pytest.raises(RepositoryError) as timestamp_error:
        repository.add(vehicle(created_at=now.replace(tzinfo=None)))
    assert timestamp_error.value.code == "REPOSITORY_TIMESTAMP_INVALID"


def test_detection_log_preserves_day8_ocr_contract_without_deciding() -> None:
    repository = InMemoryDetectionLogRepository()
    record = detection()

    repository.add(record)
    stored = repository.get_by_correlation_id(record.correlation_id)

    assert stored == record
    assert not hasattr(stored, "decision")
    assert not hasattr(stored, "authorized")


@pytest.mark.parametrize("confidence", [-0.01, 1.01, float("nan"), float("inf")])
def test_detection_log_rejects_invalid_confidence(confidence: float) -> None:
    repository = InMemoryDetectionLogRepository()

    with pytest.raises(RepositoryError) as caught:
        repository.add(detection(confidence=confidence))

    assert caught.value.code == "REPOSITORY_CONFIDENCE_INVALID"


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("recognized", "OCR_LOW_CONFIDENCE"),
        ("manual_review", None),
        ("manual_review", "UNKNOWN"),
    ],
)
def test_detection_log_rejects_inconsistent_ocr_state(
    status: str, reason: str | None
) -> None:
    repository = InMemoryDetectionLogRepository()

    with pytest.raises(RepositoryError) as caught:
        repository.add(detection(ocr_status=status, review_reason=reason))

    assert caught.value.code == "REPOSITORY_OCR_STATE_INVALID"


def test_detection_log_accepts_empty_and_low_confidence_manual_review() -> None:
    repository = InMemoryDetectionLogRepository()
    empty = detection(
        correlation_id=uuid4(),
        raw_text="",
        normalized_text="",
        confidence=None,
        ocr_status="manual_review",
        review_reason="OCR_EMPTY",
    )
    low = detection(
        correlation_id=uuid4(),
        confidence=0.2,
        ocr_status="manual_review",
        review_reason="OCR_LOW_CONFIDENCE",
    )

    repository.add(empty)
    repository.add(low)

    assert repository.get_by_correlation_id(empty.correlation_id) == empty
    assert repository.get_by_correlation_id(low.correlation_id) == low


def test_evidence_reference_is_paired_relative_and_traversal_free() -> None:
    repository = InMemoryDetectionLogRepository()
    windows_absolute_path = f"C:{chr(92)}private{chr(92)}event.png"
    valid = detection(
        evidence_bucket="plate-evidence",
        evidence_object_path="2026/07/event.png",
    )
    repository.add(valid)

    for invalid in (
        detection(correlation_id=uuid4(), evidence_bucket="plate-evidence"),
        detection(
            correlation_id=uuid4(),
            evidence_bucket="",
            evidence_object_path="event.png",
        ),
        detection(
            correlation_id=uuid4(),
            evidence_bucket="plate-evidence",
            evidence_object_path="../private.png",
        ),
        detection(
            correlation_id=uuid4(),
            evidence_bucket="plate-evidence",
            evidence_object_path="/absolute.png",
        ),
        detection(
            correlation_id=uuid4(),
            evidence_bucket="plate-evidence",
            evidence_object_path=windows_absolute_path,
        ),
    ):
        with pytest.raises(RepositoryError) as caught:
            repository.add(invalid)
        assert caught.value.code == "REPOSITORY_EVIDENCE_INVALID"


def test_duplicate_correlation_and_invalid_timings_are_rejected() -> None:
    repository = InMemoryDetectionLogRepository()
    record = detection()
    repository.add(record)

    with pytest.raises(RepositoryError) as duplicate:
        repository.add(replace(record, id=uuid4()))
    assert duplicate.value.code == "REPOSITORY_CORRELATION_DUPLICATE"
    with pytest.raises(RepositoryError) as timings:
        repository.add(detection(timings={"ocr_ms": float("nan")}))
    assert timings.value.code == "REPOSITORY_TIMINGS_INVALID"


def test_mutable_log_and_setting_values_are_copied() -> None:
    logs = InMemoryDetectionLogRepository()
    timings = {"ocr_ms": 1.0}
    log = detection(timings=timings)
    logs.add(log)
    timings["ocr_ms"] = 99.0
    assert logs.get_by_correlation_id(log.correlation_id).timings["ocr_ms"] == 1.0

    settings = InMemorySettingsRepository()
    value = {"retention_days": 30}
    record = SettingRecord("evidence.retention", value, utc_now(), utc_now())
    settings.set(record)
    value["retention_days"] = 1
    assert settings.get("evidence.retention").value == {"retention_days": 30}


def test_settings_repository_rejects_invalid_keys_and_non_json_values() -> None:
    repository = InMemorySettingsRepository()
    now = utc_now()

    with pytest.raises(RepositoryError) as key_error:
        repository.set(SettingRecord("INVALID KEY", {}, now, now))
    assert key_error.value.code == "REPOSITORY_SETTING_KEY_INVALID"
    with pytest.raises(RepositoryError) as value_error:
        repository.set(SettingRecord("valid.key", {object()}, now, now))
    assert value_error.value.code == "REPOSITORY_SETTING_VALUE_INVALID"


def test_repository_modules_and_schema_validation_require_no_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_network(*_: object, **__: object) -> None:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr("socket.create_connection", forbidden_network)
    from scripts.validate_schema import MIGRATION, validate_schema

    assert MIGRATION == (
        Path(__file__).resolve().parents[2]
        / "supabase"
        / "migrations"
        / "202607310001_day9_data_model.sql"
    )
    assert validate_schema(MIGRATION.read_text(encoding="utf-8")) == []


def test_schema_validator_rejects_missing_contract_and_embedded_secret() -> None:
    from scripts.validate_schema import validate_schema

    credential_assignment = "service_role" + "_key = " + "'placeholder'"
    failures = validate_schema(f"begin; {credential_assignment}; commit;")

    assert "missing authorized vehicles" in failures
    assert "forbidden embedded credential" in failures


def test_schema_validator_requires_durable_timing_constraint() -> None:
    from scripts.validate_schema import MIGRATION, validate_schema

    sql = MIGRATION.read_text(encoding="utf-8").replace(
        "check (public.is_nonnegative_finite_timings(timings))",
        "check (jsonb_typeof(timings) = 'object')",
    )

    assert "missing finite non-negative timings constraint" in validate_schema(sql)
