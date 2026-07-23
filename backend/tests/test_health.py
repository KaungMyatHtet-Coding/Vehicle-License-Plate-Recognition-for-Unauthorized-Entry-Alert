"""Tests for the Day 2 public endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_returns_deterministic_response() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "vehicle-license-backend",
        "version": "0.1.0",
    }


def test_api_health_compatibility_alias_returns_same_response() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "vehicle-license-backend",
        "version": "0.1.0",
    }


def test_root_endpoint_returns_api_information() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "title": "Vehicle License Plate Recognition for Unauthorized Entry Alert",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


def test_openapi_documentation_is_available() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == (
        "Vehicle License Plate Recognition for Unauthorized Entry Alert"
    )


def test_unknown_route_uses_structured_error_response() -> None:
    response = client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "HTTP_ERROR", "message": "Not Found"}}
