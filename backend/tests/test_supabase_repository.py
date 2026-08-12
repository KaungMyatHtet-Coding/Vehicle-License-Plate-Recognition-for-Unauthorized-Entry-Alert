"""Deterministic contract tests for the optional, mocked Supabase adapters."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from app.repositories.contracts import (
    AuthorizedVehicleRecord,
    DetectionLogRecord,
    RepositoryError,
)
from app.repositories.supabase_repo import (
    _detection_payload,
    _vehicle_payload,
    SupabaseAuthorizedVehicleRepository,
    SupabaseDetectionLogRepository,
)
from app.repositories.memory import utc_now
from postgrest.exceptions import APIError


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
    now = utc_now()
    record = DetectionLogRecord(
        id=uuid4(),
        correlation_id=uuid4(),
        raw_text="YGN 5A-1234",
        normalized_text="YGN5A1234",
        confidence=0.95,
        ocr_status="recognized",
        review_reason=None,
        decision="AUTHORIZED",
        decision_reason="ACTIVE_MATCH",
        matched_vehicle_id=uuid4(),
        evidence_bucket=None,
        evidence_object_path=None,
        timings={"ocr_ms": 12.5},
        created_at=now,
    )
    return replace(record, **changes)


class FakeResult:
    def __init__(self, data: list[dict[str, Any]] | None = None) -> None:
        self.data = data or []


class FakeQuery:
    def __init__(self, client: "FakeClient", table: str, operation: str) -> None:
        self.client = client
        self.table_name = table
        self.operation = operation
        self.filters: dict[str, Any] = {}
        self.payload: dict[str, Any] | None = None

    def select(self, _: str) -> "FakeQuery":
        return self

    def insert(self, payload: dict[str, Any]) -> "FakeQuery":
        self.operation = "insert"
        self.payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> "FakeQuery":
        self.operation = "update"
        self.payload = payload
        return self

    def eq(self, field: str, value: Any) -> "FakeQuery":
        self.filters[field] = value
        return self

    def order(self, _: str, *, desc: bool = False) -> "FakeQuery":
        return self

    def execute(self) -> FakeResult:
        rows = self.client.rows.setdefault(self.table_name, [])
        matches = [
            row
            for row in rows
            if all(
                str(row.get(key)) == str(value) for key, value in self.filters.items()
            )
        ]
        if self.operation == "insert":
            assert self.payload is not None
            if any(
                row["normalized_plate"] == self.payload["normalized_plate"]
                for row in rows
            ):
                raise APIError(
                    {
                        "code": "23505",
                        "message": "duplicate key value violates unique constraint",
                        "details": "provider details",
                    }
                )
            rows.append(dict(self.payload))
            return FakeResult([dict(self.payload)])
        if self.operation == "update":
            if not matches:
                return FakeResult()
            assert self.payload is not None
            matches[0].update(self.payload)
            return FakeResult([dict(matches[0])])
        return FakeResult(
            [dict(row) for row in matches]
            if self.filters
            else [dict(row) for row in rows]
        )


class FakeClient:
    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = {}
        self.calls = 0

    def table(self, name: str) -> FakeQuery:
        self.calls += 1
        operation = "select"
        return FakeQuery(self, name, operation)


def test_supabase_vehicle_and_detection_round_trip_preserves_canonical_fields() -> None:
    client = FakeClient()
    vehicles = SupabaseAuthorizedVehicleRepository(client, schema_ready=True)  # type: ignore[arg-type]
    logs = SupabaseDetectionLogRepository(client, schema_ready=True)  # type: ignore[arg-type]
    vehicle_record = vehicle()
    detection_record = detection(
        matched_vehicle_id=vehicle_record.id,
        evidence_bucket="detection-evidence",
        evidence_object_path="2026/08/event.png",
        timings={"ocr_ms": 12.5, "total_ms": 20.0},
    )

    vehicles.add(vehicle_record)
    logs.add(detection_record)

    assert (
        vehicles.get_by_normalized_plate(vehicle_record.normalized_plate)
        == vehicle_record
    )
    assert (
        logs.get_by_correlation_id(detection_record.correlation_id) == detection_record
    )


def test_supabase_vehicle_duplicate_and_unknown_update_are_safe() -> None:
    client = FakeClient()
    repository = SupabaseAuthorizedVehicleRepository(client, schema_ready=True)  # type: ignore[arg-type]
    record = vehicle()
    repository.add(record)

    with pytest.raises(RepositoryError) as duplicate:
        repository.add(replace(record, id=uuid4()))
    assert duplicate.value.code == "REPOSITORY_PLATE_DUPLICATE"

    with pytest.raises(RepositoryError) as missing:
        repository.update(replace(record, id=uuid4()))
    assert missing.value.code == "REPOSITORY_VEHICLE_NOT_FOUND"


def test_supabase_provider_errors_and_unknown_schema_are_redacted() -> None:
    class BrokenClient:
        def table(self, _: str) -> Any:
            raise RuntimeError("https://secret.example provider password")

    repository = SupabaseAuthorizedVehicleRepository(BrokenClient(), schema_ready=True)  # type: ignore[arg-type]
    with pytest.raises(RepositoryError) as provider:
        repository.get_by_id(uuid4())
    assert str(provider.value) == "Supabase vehicle lookup failed."
    assert "secret" not in str(provider.value)

    blocked = SupabaseAuthorizedVehicleRepository(BrokenClient())  # type: ignore[arg-type]
    with pytest.raises(RepositoryError) as readiness:
        blocked.get_by_id(uuid4())
    assert readiness.value.code == "SUPABASE_SCHEMA_NOT_READY"


def test_message_only_duplicate_is_generic_and_redacted() -> None:
    class MessageOnlyDuplicateClient(FakeClient):
        def table(self, name: str) -> FakeQuery:
            query = super().table(name)
            if name == "authorized_vehicles":

                def fail(_: dict[str, Any]) -> FakeQuery:
                    query.operation = "insert"
                    query.payload = _vehicle_payload(vehicle())
                    return query

                query.insert = fail  # type: ignore[method-assign]
                query.execute = lambda: (_ for _ in ()).throw(  # type: ignore[method-assign]
                    APIError(
                        {
                            "code": None,
                            "message": "duplicate provider secret URL",
                            "details": "private SQL details",
                        }
                    )
                )
            return query

    repository = SupabaseAuthorizedVehicleRepository(
        MessageOnlyDuplicateClient(),
        schema_ready=True,  # type: ignore[arg-type]
    )
    with pytest.raises(RepositoryError) as caught:
        repository.add(vehicle())
    assert caught.value.code == "SUPABASE_ERROR"
    assert str(caught.value) == "Supabase vehicle insert failed."


def test_invalid_vehicle_writes_are_rejected_before_provider_invocation() -> None:
    client = FakeClient()
    repository = SupabaseAuthorizedVehicleRepository(client, schema_ready=True)  # type: ignore[arg-type]
    now = utc_now()
    invalid_records = [
        vehicle(normalized_plate="bad plate"),
        vehicle(status="ACTIVE"),
        vehicle(created_at=datetime(2026, 1, 1)),
        vehicle(updated_at=datetime(2026, 1, 1)),
        vehicle(valid_from=now, valid_until=now),
    ]

    for record in invalid_records:
        with pytest.raises(RepositoryError):
            repository.add(record)
    with pytest.raises(RepositoryError):
        repository.update(vehicle(id=uuid4(), created_at=datetime(2026, 1, 1)))
    assert client.calls == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"timings": {"ocr_ms": -1.0}},
        {"timings": {"ocr_ms": float("nan")}},
        {"ocr_status": "recognized", "review_reason": "OCR_EMPTY"},
        {"decision": "AUTHORIZED", "decision_reason": "VEHICLE_NOT_FOUND"},
        {"evidence_bucket": "evidence-only", "evidence_object_path": None},
        {"created_at": datetime(2026, 1, 1)},
    ],
)
def test_invalid_detection_writes_are_rejected_before_provider_invocation(
    changes: dict[str, Any],
) -> None:
    client = FakeClient()
    repository = SupabaseDetectionLogRepository(client, schema_ready=True)  # type: ignore[arg-type]

    with pytest.raises(RepositoryError):
        repository.add(detection(**changes))
    assert client.calls == 0


def test_detection_unique_violation_remains_generic_without_constraint_identity() -> (
    None
):
    class DuplicateDetectionClient(FakeClient):
        def table(self, name: str) -> FakeQuery:
            query = super().table(name)
            if name == "detection_logs":
                query.execute = lambda: (_ for _ in ()).throw(  # type: ignore[method-assign]
                    APIError(
                        {
                            "code": "23505",
                            "message": "duplicate provider detail",
                            "details": "private constraint detail",
                        }
                    )
                )
            return query

    repository = SupabaseDetectionLogRepository(
        DuplicateDetectionClient(),
        schema_ready=True,  # type: ignore[arg-type]
    )
    with pytest.raises(RepositoryError) as caught:
        repository.add(detection())
    assert caught.value.code == "SUPABASE_ERROR"
    assert str(caught.value) == "Supabase detection-log insert failed."


def test_malformed_vehicle_rows_fail_closed_without_fabricated_timestamps() -> None:
    cases = [
        {"id": "not-a-uuid"},
        {"status": "ACTIVE"},
        {"created_at": None},
        {"updated_at": "not-a-timestamp"},
    ]
    for changes in cases:
        record = vehicle()
        client = FakeClient()
        client.rows["authorized_vehicles"] = [{**_vehicle_payload(record), **changes}]
        repository = SupabaseAuthorizedVehicleRepository(client, schema_ready=True)  # type: ignore[arg-type]
        with pytest.raises(RepositoryError) as caught:
            repository.get_by_normalized_plate(record.normalized_plate)
        assert caught.value.code in {
            "SUPABASE_ROW_INVALID",
            "REPOSITORY_STATUS_INVALID",
        }
        assert "not-a" not in str(caught.value)


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "not-a-uuid"},
        {"created_at": ""},
        {"evidence_bucket": "bucket-only", "evidence_object_path": None},
        {"timings": {"ocr_ms": -1.0}},
        {"timings": {"ocr_ms": float("nan")}},
        {"ocr_status": "recognized", "review_reason": "OCR_EMPTY"},
        {"decision": "AUTHORIZED", "decision_reason": "VEHICLE_NOT_FOUND"},
        {"decision": "AUTHORIZED", "matched_vehicle_id": None},
    ],
)
def test_malformed_detection_rows_fail_closed(changes: dict[str, Any]) -> None:
    record = detection()
    client = FakeClient()
    client.rows["detection_logs"] = [{**_detection_payload(record), **changes}]
    repository = SupabaseDetectionLogRepository(client, schema_ready=True)  # type: ignore[arg-type]

    with pytest.raises(RepositoryError) as caught:
        repository.get_by_correlation_id(record.correlation_id)
    assert caught.value.code in {
        "SUPABASE_ROW_INVALID",
        "REPOSITORY_EVIDENCE_INVALID",
        "REPOSITORY_TIMINGS_INVALID",
        "REPOSITORY_OCR_STATE_INVALID",
        "REPOSITORY_DECISION_INVALID",
    }
    assert "not-a" not in str(caught.value)
