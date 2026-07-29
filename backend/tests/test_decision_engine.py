"""Focused Day 10 tests for deterministic, explainable entry decisions."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.repositories.contracts import AuthorizedVehicleRecord, RepositoryError
from app.repositories.memory import InMemoryAuthorizedVehicleRepository
from app.schemas.decision import EntryDecision
from app.schemas.ocr import PlateOcrResponse
from app.services.authorization_decision import AuthorizationDecisionService

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
CORRELATION_ID = "9fe3d1ef-9518-4775-89d8-b97c884f1522"


def ocr(**changes: object) -> PlateOcrResponse:
    values: dict[str, object] = {
        "correlation_id": CORRELATION_ID,
        "status": "recognized",
        "review_reason": None,
        "raw_text": "YGN 5A-1234",
        "normalized_text": "YGN5A1234",
        "confidence": 0.95,
        "mode": "recognition_only",
        "inference_ms": 1.0,
        "total_ms": 2.0,
        "image_width": 200,
        "image_height": 50,
    }
    values.update(changes)
    return PlateOcrResponse.model_construct(**values)


def vehicle(**changes: object) -> AuthorizedVehicleRecord:
    record = AuthorizedVehicleRecord(
        id=uuid4(),
        normalized_plate="YGN5A1234",
        status="active",
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=1),
        created_at=NOW - timedelta(days=2),
        updated_at=NOW - timedelta(days=1),
    )
    return replace(record, **changes)


def service(
    record: AuthorizedVehicleRecord | None = None,
    *,
    minimum_confidence: float = 0.80,
    clock: object = None,
) -> AuthorizationDecisionService:
    repository = InMemoryAuthorizedVehicleRepository()
    if record is not None:
        repository.add(record)
    return AuthorizationDecisionService(
        repository,
        Settings(DECISION_MIN_CONFIDENCE=minimum_confidence),
        clock=clock if callable(clock) else lambda: NOW,
    )


def test_active_exact_match_inside_validity_is_authorized() -> None:
    record = vehicle()

    result = service(record).decide(ocr())

    assert result.decision == "AUTHORIZED"
    assert result.reason == "ACTIVE_MATCH"
    assert result.vehicle_id == record.id
    assert result.evaluated_at == NOW
    assert result.correlation_id == CORRELATION_ID


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (0.799999, "MANUAL_REVIEW"),
        (0.80, "AUTHORIZED"),
        (0.800001, "AUTHORIZED"),
    ],
)
def test_confidence_threshold_boundary(confidence: float, expected: str) -> None:
    result = service(vehicle()).decide(ocr(confidence=confidence))

    assert result.decision == expected
    assert result.reason == (
        "OCR_LOW_CONFIDENCE" if expected == "MANUAL_REVIEW" else "ACTIVE_MATCH"
    )


def test_empty_ocr_is_manual_review_without_lookup() -> None:
    class NoLookupRepository:
        def get_by_normalized_plate(self, _: str) -> None:
            raise AssertionError("empty OCR must not perform lookup")

    result = AuthorizationDecisionService(
        NoLookupRepository(), Settings(), lambda: NOW
    ).decide(
        ocr(
            status="manual_review",
            review_reason="OCR_EMPTY",
            raw_text="",
            normalized_text="",
            confidence=None,
        )
    )

    assert result.decision == "MANUAL_REVIEW"
    assert result.reason == "OCR_EMPTY"
    assert result.vehicle_id is None


def test_day8_low_confidence_is_manual_review_without_lookup() -> None:
    class NoLookupRepository:
        def get_by_normalized_plate(self, _: str) -> None:
            raise AssertionError("low-confidence OCR must not perform lookup")

    result = AuthorizationDecisionService(
        NoLookupRepository(), Settings(), lambda: NOW
    ).decide(
        ocr(
            status="manual_review",
            review_reason="OCR_LOW_CONFIDENCE",
            confidence=0.2,
        )
    )

    assert result.decision == "MANUAL_REVIEW"
    assert result.reason == "OCR_LOW_CONFIDENCE"


@pytest.mark.parametrize(
    "invalid_ocr",
    [
        ocr(normalized_text="YGN-5A1234"),
        ocr(confidence=float("nan")),
        ocr(confidence=float("inf")),
        ocr(confidence=-0.01),
        ocr(confidence=1.01),
        ocr(confidence=True),
        PlateOcrResponse.model_construct(),
        ocr(normalized_text=123),
        ocr(status="recognized", review_reason="OCR_LOW_CONFIDENCE"),
        ocr(
            status="manual_review",
            review_reason="OCR_EMPTY",
            normalized_text="YGN5A1234",
        ),
    ],
)
def test_malformed_ocr_never_authorizes(invalid_ocr: PlateOcrResponse) -> None:
    result = service(vehicle()).decide(invalid_ocr)

    assert result.decision == "MANUAL_REVIEW"
    assert result.reason == "OCR_RESULT_INVALID"


def test_unknown_plate_is_explicit_non_accusatory_unauthorized() -> None:
    result = service().decide(ocr())

    assert result.decision == "UNAUTHORIZED"
    assert result.reason == "VEHICLE_NOT_FOUND"
    assert "accus" not in result.message.lower()
    assert result.vehicle_id is None


def test_unsafe_correlation_id_is_not_copied_to_public_result() -> None:
    unsafe = f"D:{chr(92)}private{chr(92)}request"

    result = service().decide(ocr(correlation_id=unsafe))

    assert result.correlation_id == ""
    assert unsafe not in result.model_dump_json()


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("inactive", "VEHICLE_INACTIVE"),
        ("blocked", "VEHICLE_BLOCKED"),
    ],
)
def test_non_active_record_states_do_not_permit_entry(status: str, reason: str) -> None:
    result = service(vehicle(status=status)).decide(ocr())

    assert result.decision == "UNAUTHORIZED"
    assert result.reason == reason
    assert "wrongdoing" not in result.message.lower()


def test_validity_boundaries_are_timezone_aware_and_deterministic() -> None:
    at_start = service(vehicle(valid_from=NOW), clock=lambda: NOW).decide(ocr())
    before_end = service(
        vehicle(valid_until=NOW + timedelta(microseconds=1)), clock=lambda: NOW
    ).decide(ocr())
    at_end = service(vehicle(valid_until=NOW), clock=lambda: NOW).decide(ocr())
    after_end = service(
        vehicle(valid_until=NOW - timedelta(microseconds=1)), clock=lambda: NOW
    ).decide(ocr())
    before_start = service(
        vehicle(valid_from=NOW + timedelta(microseconds=1)), clock=lambda: NOW
    ).decide(ocr())

    assert (at_start.decision, at_start.reason) == ("AUTHORIZED", "ACTIVE_MATCH")
    assert (before_end.decision, before_end.reason) == ("AUTHORIZED", "ACTIVE_MATCH")
    assert (at_end.decision, at_end.reason) == ("UNAUTHORIZED", "VEHICLE_EXPIRED")
    assert (after_end.decision, after_end.reason) == (
        "UNAUTHORIZED",
        "VEHICLE_EXPIRED",
    )
    assert (before_start.decision, before_start.reason) == (
        "UNAUTHORIZED",
        "VEHICLE_NOT_YET_VALID",
    )


class FixedRepository:
    def __init__(self, record: object) -> None:
        self.record = record

    def get_by_normalized_plate(self, _: str) -> object:
        return self.record


@pytest.mark.parametrize(
    "record",
    [
        object(),
        vehicle(id="not-a-uuid"),
        vehicle(normalized_plate="OTHER123"),
        vehicle(created_at=NOW.replace(tzinfo=None)),
        vehicle(valid_from=(NOW - timedelta(days=1)).replace(tzinfo=None)),
        vehicle(valid_from=NOW, valid_until=NOW),
    ],
)
def test_malformed_repository_record_fails_to_manual_review(record: object) -> None:
    result = AuthorizationDecisionService(
        FixedRepository(record), Settings(), lambda: NOW
    ).decide(ocr())

    assert result.decision == "MANUAL_REVIEW"
    assert result.reason == "VEHICLE_RECORD_INVALID"
    assert result.vehicle_id is None


def test_repository_failure_never_grants_entry_or_exposes_details() -> None:
    class FailingRepository:
        def get_by_normalized_plate(self, _: str) -> None:
            private_path = f"D:{chr(92)}private{chr(92)}credential.json"
            raise RepositoryError(
                "SUPABASE_PRIVATE_FAILURE",
                private_path,
            )

    result = AuthorizationDecisionService(
        FailingRepository(), Settings(), lambda: NOW
    ).decide(ocr())

    assert result.decision == "MANUAL_REVIEW"
    assert result.reason == "VEHICLE_LOOKUP_FAILED"
    assert "D:\\" not in result.message
    assert "SUPABASE" not in result.message


@pytest.mark.parametrize(
    "clock",
    [
        lambda: datetime(2026, 8, 1),
        lambda: (_ for _ in ()).throw(RuntimeError("private clock failure")),
    ],
)
def test_invalid_or_failed_clock_never_grants_entry(clock: object) -> None:
    result = service(vehicle(), clock=clock).decide(ocr())

    assert result.decision == "MANUAL_REVIEW"
    assert result.reason == "DECISION_TIME_INVALID"


def test_decision_service_has_no_network_filesystem_or_action_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_: object, **__: object) -> None:
        raise AssertionError("side effect attempted")

    monkeypatch.setattr("socket.create_connection", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)

    result = service(vehicle()).decide(ocr())

    assert result.decision == "AUTHORIZED"
    assert not hasattr(result, "gate")
    assert not hasattr(result, "alert")
    assert not hasattr(result, "accusation")


def test_decision_threshold_setting_is_bounded() -> None:
    assert Settings().decision_min_confidence == 0.80
    with pytest.raises(ValueError):
        Settings(DECISION_MIN_CONFIDENCE=-0.01)
    with pytest.raises(ValueError):
        Settings(DECISION_MIN_CONFIDENCE=1.01)
    with pytest.raises(ValueError):
        Settings(DECISION_MIN_CONFIDENCE=True)
    with pytest.raises(ValueError):
        Settings(DECISION_MIN_CONFIDENCE=float("nan"))
    with pytest.raises(ValueError):
        Settings(DECISION_MIN_CONFIDENCE=float("inf"))


def test_entry_decision_schema_requires_timezone_aware_evaluation() -> None:
    with pytest.raises(ValidationError):
        EntryDecision(
            correlation_id=CORRELATION_ID,
            decision="MANUAL_REVIEW",
            reason="DECISION_TIME_INVALID",
            message="Manual review is required.",
            normalized_plate="",
            confidence=None,
            vehicle_id=None,
            evaluated_at=NOW.replace(tzinfo=None),
        )
