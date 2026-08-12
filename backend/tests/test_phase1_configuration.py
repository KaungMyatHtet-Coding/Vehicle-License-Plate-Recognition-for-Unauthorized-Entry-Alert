"""Phase 1 tests for explicit localhost configuration and dependency isolation."""

from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.dependencies import (
    build_application_dependencies,
    get_application_dependencies,
    reset_application_dependencies,
)
from app.main import app
from app.repositories.memory import (
    InMemoryAuthorizedVehicleRepository,
    InMemoryDetectionLogRepository,
    InMemoryRecognitionActivityRepository,
)


def isolated_settings(**values: object) -> Settings:
    """Construct settings without dotenv input while retaining safe test env."""

    return Settings(_env_file=None, **values)


def test_default_test_configuration_ignores_local_dotenv_for_repository_mode() -> None:
    settings = get_settings()
    assert settings.app_mode == "localhost"
    assert settings.repository_mode == "memory"
    assert settings.enable_experimental_video is False
    assert settings.supabase_url is None
    assert settings.supabase_service_role_key is None


def test_memory_mode_builds_one_coherent_shared_adapter_set() -> None:
    settings = isolated_settings(REPOSITORY_MODE="memory")
    built = build_application_dependencies(settings)
    assert isinstance(built.vehicles, InMemoryAuthorizedVehicleRepository)
    assert isinstance(built.detection_logs, InMemoryDetectionLogRepository)
    assert isinstance(built.recognition_activity, InMemoryRecognitionActivityRepository)

    reset_application_dependencies()
    first = get_application_dependencies()
    second = get_application_dependencies()
    assert first is second


def test_supabase_mode_requires_complete_configuration() -> None:
    with pytest.raises(ValidationError, match="configuration is incomplete"):
        isolated_settings(REPOSITORY_MODE="supabase")


def test_supabase_initialization_failure_is_redacted_and_never_falls_back() -> None:
    settings = isolated_settings(
        REPOSITORY_MODE="supabase",
        SUPABASE_URL="https://example.invalid",
        SUPABASE_SERVICE_ROLE_KEY="test-placeholder-not-a-secret",
    )

    def fail_without_network(_: str, __: str) -> object:
        raise RuntimeError("provider detail must remain private")

    with pytest.raises(RuntimeError) as raised:
        build_application_dependencies(
            settings, supabase_client_factory=fail_without_network
        )
    assert str(raised.value) == "Supabase repository initialization failed."
    assert "provider" not in str(raised.value)
    assert raised.value.__cause__ is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("APP_HOST", "0.0.0.0"),
        ("FRONTEND_ORIGINS", "https://public.example"),
    ],
)
def test_localhost_mode_rejects_non_loopback_boundaries(field: str, value: str) -> None:
    with pytest.raises(ValidationError, match="loopback"):
        isolated_settings(**{field: value})


def test_default_application_keeps_still_image_routes_and_disables_video() -> None:
    paths = app.openapi()["paths"]
    assert "/api/recognition/analyze" in paths
    assert "/api/authorized-vehicles" in paths
    assert "/api/dashboard/statistics" in paths
    assert "/api/detections" in paths
    assert "/api/alerts" in paths
    assert "/health" in paths
    assert "/api/recognition/analyze-video" not in paths
    assert TestClient(app).post("/api/recognition/analyze-video").status_code == 404


def test_external_network_guard_is_active() -> None:
    with pytest.raises(AssertionError, match="External network"):
        socket.create_connection(("203.0.113.1", 443), timeout=0.01)
