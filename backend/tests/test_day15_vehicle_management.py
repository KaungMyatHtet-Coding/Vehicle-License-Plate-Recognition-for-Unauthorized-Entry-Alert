"""Focused deterministic Day 15 vehicle-management tests."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.routes.vehicles import get_service
from app.main import app
from app.repositories.memory import InMemoryAuthorizedVehicleRepository
from app.core.config import Settings
from app.schemas.ocr import PlateOcrResponse
from app.schemas.vehicles import VehicleCreate, VehicleUpdate
from app.services.authorization_decision import AuthorizationDecisionService
from app.services.vehicle_management import VehicleManagementService

NOW = datetime(2026, 8, 6, 12, tzinfo=timezone.utc)


def service() -> VehicleManagementService:
    return VehicleManagementService(
        InMemoryAuthorizedVehicleRepository(), clock=lambda: NOW
    )


def test_create_normalizes_and_duplicate_fails_closed() -> None:
    manager = service()
    created = manager.create(
        VehicleCreate(plate_number=" ygn 5a-1234 ", description="  Visitor  ")
    )
    assert created.normalized_plate == "YGN5A1234"
    assert created.status == "ACTIVE"
    try:
        manager.create(VehicleCreate(plate_number="YGN5A1234"))
        raise AssertionError("duplicate was accepted")
    except RuntimeError as exc:
        assert getattr(exc, "code") == "VEHICLE_DUPLICATE"


def test_search_filter_update_and_status_are_deterministic() -> None:
    manager = service()
    first = manager.create(VehicleCreate(plate_number="ABC-123"))
    second = manager.create(VehicleCreate(plate_number="XYZ-789", status="BLOCKED"))
    assert [item.id for item in manager.list("bc1")] == [first.id]
    assert [item.id for item in manager.list(status="BLOCKED")] == [second.id]
    updated = manager.update(
        first.id,
        VehicleUpdate(
            plate_number="ABC-124",
            description="Staff",
            status="INACTIVE",
            valid_from=NOW,
            valid_until=NOW + timedelta(days=1),
        ),
    )
    assert (
        updated
        and updated.normalized_plate == "ABC124"
        and updated.status == "INACTIVE"
    )
    blocked = manager.status(first.id, "BLOCKED")
    assert blocked and blocked.status == "BLOCKED" and manager.get(first.id) == blocked


def test_status_change_changes_later_authoritative_decision() -> None:
    repository = InMemoryAuthorizedVehicleRepository()
    manager = VehicleManagementService(repository, clock=lambda: NOW)
    vehicle = manager.create(VehicleCreate(plate_number="ABC123"))
    decision = AuthorizationDecisionService(repository, Settings(), clock=lambda: NOW)
    ocr = PlateOcrResponse(
        correlation_id=str(uuid4()),
        raw_text="ABC123",
        normalized_text="ABC123",
        confidence=0.99,
        status="recognized",
        review_reason=None,
        mode="recognition_only",
        inference_ms=1,
        total_ms=1,
        image_width=100,
        image_height=40,
    )
    assert decision.decide(ocr).decision == "AUTHORIZED"
    manager.status(vehicle.id, "BLOCKED")
    result = decision.decide(ocr)
    assert result.decision == "UNAUTHORIZED" and result.reason == "VEHICLE_BLOCKED"

    expired = manager.create(
        VehicleCreate(
            plate_number="OLD123",
            valid_from=NOW - timedelta(days=2),
            valid_until=NOW - timedelta(days=1),
        )
    )
    expired_ocr = ocr.model_copy(
        update={"normalized_text": expired.normalized_plate, "raw_text": "OLD123"}
    )
    expired_result = decision.decide(expired_ocr)
    assert expired_result.decision == "UNAUTHORIZED"
    assert expired_result.reason == "VEHICLE_EXPIRED"


def test_api_crud_filters_validation_conflict_and_not_found_are_sanitized() -> None:
    manager = service()
    app.dependency_overrides[get_service] = lambda: manager
    try:
        client = TestClient(app)
        created = client.post(
            "/api/authorized-vehicles",
            json={"plate_number": "ABC-123", "status": "ACTIVE"},
        )
        assert created.status_code == 201
        vehicle_id = created.json()["id"]
        assert (
            client.get(
                "/api/authorized-vehicles",
                params={"search": "ABC", "status_filter": "ACTIVE"},
            ).json()["total_items"]
            == 1
        )
        assert client.get(f"/api/authorized-vehicles/{vehicle_id}").status_code == 200
        assert (
            client.put(
                f"/api/authorized-vehicles/{vehicle_id}",
                json={"plate_number": "ABC124", "status": "INACTIVE"},
            ).json()["status"]
            == "INACTIVE"
        )
        assert (
            client.patch(
                f"/api/authorized-vehicles/{vehicle_id}/status",
                json={"status": "BLOCKED"},
            ).json()["status"]
            == "BLOCKED"
        )
        conflict = client.post(
            "/api/authorized-vehicles", json={"plate_number": "ABC124"}
        )
        assert conflict.status_code == 409 and "repository" not in conflict.text.lower()
        assert (
            client.post(
                "/api/authorized-vehicles", json={"plate_number": "---"}
            ).status_code
            == 422
        )
        missing = client.get(f"/api/authorized-vehicles/{uuid4()}")
        assert missing.status_code == 404 and "path" not in missing.text.lower()
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_validity_and_extra_fields_fail_validation() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/authorized-vehicles",
            json={
                "plate_number": "ABC123",
                "valid_from": NOW.isoformat(),
                "valid_until": (NOW - timedelta(days=1)).isoformat(),
                "private_key": "secret",
            },
        )
        assert response.status_code == 422
        assert "secret" not in response.text
