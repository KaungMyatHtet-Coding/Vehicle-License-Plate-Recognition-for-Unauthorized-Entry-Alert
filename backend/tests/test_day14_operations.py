"""Focused deterministic tests for Day 14 operational reads."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes.operations import get_detection_query_service
from app.main import app
from app.repositories.contracts import DetectionLogRecord
from app.repositories.memory import (
    InMemoryDetectionLogRepository,
    InMemoryRecognitionActivityRepository,
)
from app.schemas.detection import ImageDetectionResponse
from app.services.detection_queries import DetectionQueryService
from app.services.recognition_orchestration import RecognitionOrchestrationService

NOW = datetime(2026, 8, 5, 12, tzinfo=timezone.utc)


def record(
    *,
    decision="UNAUTHORIZED",
    reason="VEHICLE_NOT_FOUND",
    created_at=NOW,
    correlation_id=None,
    plate="ABC123",
    evidence=False,
) -> DetectionLogRecord:
    return DetectionLogRecord(
        id=uuid4(),
        correlation_id=correlation_id or uuid4(),
        raw_text=plate,
        normalized_text=plate,
        confidence=0.91,
        ocr_status="recognized",
        review_reason=None,
        decision=decision,
        decision_reason=reason,
        matched_vehicle_id=uuid4() if decision == "AUTHORIZED" else None,
        evidence_bucket="private-bucket" if evidence else None,
        evidence_object_path="private/path.jpg" if evidence else None,
        timings={"ocr_ms": 2.0},
        created_at=created_at,
    )


def service(*records: DetectionLogRecord) -> DetectionQueryService:
    logs = InMemoryDetectionLogRepository()
    for item in records:
        logs.add(item)
    return DetectionQueryService(
        logs, InMemoryRecognitionActivityRepository(), clock=lambda: NOW
    )


def test_history_is_newest_first_with_stable_correlation_tie_breaker() -> None:
    lower = record(correlation_id=UUID("00000000-0000-4000-8000-000000000001"))
    higher = record(correlation_id=UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"))
    older = record(created_at=NOW - timedelta(seconds=1))
    result = service(lower, older, higher).history(page=1, page_size=10)
    assert [item.correlation_id for item in result.items] == [
        str(higher.correlation_id),
        str(lower.correlation_id),
        str(older.correlation_id),
    ]


def test_history_pagination_and_filters() -> None:
    unauthorized = record(plate="ABC123")
    authorized = record(
        decision="AUTHORIZED",
        reason="ACTIVE_MATCH",
        plate="XYZ789",
        created_at=NOW - timedelta(hours=1),
    )
    query = service(unauthorized, authorized)
    assert query.history(page=1, page_size=1).total_pages == 2
    assert query.history(page=2, page_size=1).items[0].decision == "AUTHORIZED"
    assert query.history(page=1, page_size=10, decision="UNAUTHORIZED").total_items == 1
    assert (
        query.history(page=1, page_size=10, normalized_plate="XYZ789").items[0].decision
        == "AUTHORIZED"
    )
    assert (
        query.history(
            page=1, page_size=10, created_from=NOW - timedelta(minutes=30)
        ).total_items
        == 1
    )
    assert query.history(page=1, page_size=10, created_to=NOW).total_items == 1


def test_detail_is_sanitized_and_reports_restricted_evidence() -> None:
    item = record(evidence=True)
    result = service(item).detail(item.correlation_id)
    assert result is not None and result.evidence_available
    payload = result.model_dump(mode="json")
    assert payload["evidence_access"] == "restricted"
    assert (
        not {
            "evidence_bucket",
            "evidence_object_path",
            "bucket",
            "object_path",
            "token",
            "signed_access",
        }
        & payload.keys()
    )


def test_statistics_include_empty_utc_seven_day_trend() -> None:
    result = service().statistics()
    assert (
        result.total_recognitions
        == result.authorized
        == result.unauthorized
        == result.manual_review
        == result.no_plate
        == 0
    )
    assert result.timezone == "UTC" and len(result.trend) == 7


def test_statistics_totals_no_plate_and_utc_bucket_boundaries() -> None:
    logs = InMemoryDetectionLogRepository()
    activity = InMemoryRecognitionActivityRepository()
    logs.add(
        record(
            decision="AUTHORIZED",
            reason="ACTIVE_MATCH",
            created_at=datetime(2026, 8, 5, 0, tzinfo=timezone.utc),
        )
    )
    logs.add(record(created_at=datetime(2026, 8, 4, 23, 59, 59, tzinfo=timezone.utc)))
    activity.add_no_plate(uuid4(), datetime(2026, 8, 5, 1, tzinfo=timezone.utc))
    result = DetectionQueryService(logs, activity, clock=lambda: NOW).statistics()
    assert (
        result.total_recognitions,
        result.authorized,
        result.unauthorized,
        result.no_plate,
    ) == (3, 1, 1, 1)
    assert result.trend[-1].total == 2 and result.trend[-2].total == 1


def test_alerts_are_backend_selected_and_paginated() -> None:
    result = service(
        record(),
        record(decision="MANUAL_REVIEW", reason="PLATE_REGION_MISSING"),
        record(decision="AUTHORIZED", reason="ACTIVE_MATCH"),
    ).alerts(page=1, page_size=10)
    assert result.total_items == 2
    assert {item.decision for item in result.items} == {"UNAUTHORIZED", "MANUAL_REVIEW"}
    by_decision = {item.decision: item for item in result.items}
    assert by_decision["UNAUTHORIZED"].alert_type == "ENTRY_NOT_AUTHORIZED"
    assert by_decision["MANUAL_REVIEW"].alert_type == "MANUAL_REVIEW"
    assert "driver" not in by_decision["UNAUTHORIZED"].message.lower()


@pytest.mark.parametrize(
    "path",
    [
        "/api/detections?page=0",
        "/api/detections?page_size=101",
        "/api/detections?decision=OTHER",
        "/api/detections?normalized_plate=abc-123",
        "/api/detections?created_from=2026-08-05T12:00:00Z&created_to=2026-08-05T11:00:00Z",
    ],
)
def test_invalid_queries_return_safe_validation(path: str) -> None:
    response = TestClient(app).get(path)
    assert response.status_code == 422
    assert "private" not in response.text.lower()


def test_routes_return_sanitized_history_detail_and_not_found() -> None:
    item = record(evidence=True)
    app.dependency_overrides[get_detection_query_service] = lambda: service(item)
    try:
        client = TestClient(app)
        history = client.get("/api/detections").json()
        detail = client.get(f"/api/detections/{item.correlation_id}").json()
        missing = client.get(f"/api/detections/{uuid4()}")
    finally:
        app.dependency_overrides.clear()
    forbidden = {
        "evidence_bucket",
        "evidence_object_path",
        "bucket",
        "object_path",
        "token",
        "signed_access",
    }
    assert not forbidden & set(str(history).replace("'", '"').split('"'))
    assert not forbidden & set(str(detail).replace("'", '"').split('"'))
    assert (
        missing.status_code == 404
        and missing.json()["error"]["message"] == "The detection record was not found."
    )


def test_repository_failure_is_sanitized() -> None:
    class Failed:
        def history(self, **_: object):
            raise RuntimeError("provider secret /internal/path")

    app.dependency_overrides[get_detection_query_service] = lambda: Failed()
    try:
        response = TestClient(app).get("/api/detections")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert "secret" not in response.text and "internal" not in response.text


@pytest.mark.parametrize(
    ("path", "method_name", "public_message"),
    [
        (
            f"/api/detections/{UUID('11111111-1111-4111-8111-111111111111')}",
            "detail",
            "Detection history is temporarily unavailable.",
        ),
        (
            "/api/dashboard/statistics",
            "statistics",
            "Dashboard statistics are temporarily unavailable.",
        ),
        ("/api/alerts", "alerts", "Alerts are temporarily unavailable."),
    ],
)
def test_operational_endpoint_failures_are_sanitized(
    path: str, method_name: str, public_message: str
) -> None:
    class Failed:
        pass

    def fail(*_: object, **__: object) -> None:
        raise RuntimeError(
            "repository provider /private/path bucket object_key token credential secret"
        )

    setattr(Failed, method_name, fail)
    app.dependency_overrides[get_detection_query_service] = Failed
    try:
        response = TestClient(app).get(path)
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "HTTP_ERROR", "message": public_message}
    }
    forbidden = (
        "repository",
        "provider",
        "private/path",
        "bucket",
        "object_key",
        "token",
        "credential",
        "secret",
    )
    assert all(value not in response.text.lower() for value in forbidden)


def test_shared_dependency_singleton_is_used_by_recognition_and_reads() -> None:
    from app.dependencies import get_application_dependencies

    first = get_application_dependencies()
    second = get_application_dependencies()
    assert first is second
    query = DetectionQueryService(
        first.detection_logs, first.recognition_activity, clock=lambda: NOW
    )
    unique = record(correlation_id=uuid4())
    first.detection_logs.add(unique)
    assert query.detail(unique.correlation_id) is not None

    class NoPlateDetector:
        def detect(self, _: bytes, correlation_id: str) -> ImageDetectionResponse:
            return ImageDetectionResponse(
                correlation_id=correlation_id,
                status="no_plate_detected",
                detection_count=0,
                image_width=100,
                image_height=50,
                inference_ms=1.0,
                total_ms=1.0,
                detections=[],
            )

    before = query.statistics().no_plate
    recognition = RecognitionOrchestrationService(
        NoPlateDetector(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        first.recognition_activity,
    )
    result = recognition.recognize(b"transient", str(uuid4()))
    assert result.status == "no_plate_detected"
    assert query.statistics().no_plate == before + 1


def test_no_plate_ledger_failure_is_safely_observable_without_changing_result(
    caplog: pytest.LogCaptureFixture,
) -> None:
    correlation_id = "22222222-2222-4222-8222-222222222222"

    class NoPlateDetector:
        def detect(self, _: bytes, supplied_id: str) -> ImageDetectionResponse:
            return ImageDetectionResponse(
                correlation_id=supplied_id,
                status="no_plate_detected",
                detection_count=0,
                image_width=100,
                image_height=50,
                inference_ms=1.0,
                total_ms=1.0,
                detections=[],
            )

    class FailedActivity:
        def add_no_plate(self, *_: object) -> None:
            raise RuntimeError(
                "provider secret /private/path bucket object_key token credential"
            )

    recognition = RecognitionOrchestrationService(
        NoPlateDetector(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        FailedActivity(),  # type: ignore[arg-type]
    )
    with caplog.at_level("WARNING"):
        result = recognition.recognize(b"transient", correlation_id)

    assert result.status == "no_plate_detected"
    assert result.logging is None
    assert result.model_dump(mode="json")["message"].startswith(
        "No license plate was detected"
    )
    assert correlation_id in caplog.text
    assert "NO_PLATE_ACTIVITY_PERSISTENCE_FAILED" in caplog.text
    forbidden = (
        "provider secret",
        "private/path",
        "bucket",
        "object_key",
        "token",
        "credential",
    )
    assert all(value not in caplog.text for value in forbidden)
    assert all(value not in result.model_dump_json() for value in forbidden)
