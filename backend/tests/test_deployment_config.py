"""Day 19 tests for free-tier deployment configuration and invariants."""

from __future__ import annotations

import os
import re

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_dockerfile_exists_and_valid() -> None:
    """backend/Dockerfile exists and contains required production configuration."""
    dockerfile_path = os.path.join(_ROOT, "backend", "Dockerfile")
    assert os.path.isfile(dockerfile_path), "backend/Dockerfile must exist"

    with open(dockerfile_path, encoding="utf-8") as f:
        content = f.read()

    assert "FROM python:3.12" in content
    assert "EXPOSE 8000" in content
    assert "HEALTHCHECK" in content
    assert "useradd" in content or "USER appuser" in content
    assert "uvicorn app.main:app" in content


def test_render_yaml_exists_and_valid() -> None:
    """render.yaml blueprint exists and defines free-tier backend service."""
    render_yaml_path = os.path.join(_ROOT, "render.yaml")
    assert os.path.isfile(render_yaml_path), "render.yaml must exist"

    with open(render_yaml_path, encoding="utf-8") as f:
        content = f.read()

    assert "cvpx-backend" in content
    assert "docker" in content
    assert "plan: free" in content
    assert "healthCheckPath: /health" in content


test_supabase_migration_exists_and_valid_data = (
    "authorized_vehicles",
    "detection_logs",
    "recognition_activity",
)


@pytest.mark.parametrize("table_name", test_supabase_migration_exists_and_valid_data)
def test_supabase_migration_schema(table_name: str) -> None:
    """Supabase migration script defines all required application tables and RLS."""
    migration_path = os.path.join(
        _ROOT, "supabase", "migrations", "20260802000000_initial_schema.sql"
    )
    assert os.path.isfile(migration_path), "Supabase migration SQL file must exist"

    with open(migration_path, encoding="utf-8") as f:
        content = f.read()

    assert f"CREATE TABLE IF NOT EXISTS public.{table_name}" in content
    assert f"ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY" in content


def test_deployment_guide_exists_and_secret_free() -> None:
    """docs/deployment.md exists and contains no hardcoded secrets or API keys."""
    guide_path = os.path.join(_ROOT, "docs", "deployment.md")
    assert os.path.isfile(guide_path), "docs/deployment.md must exist"

    with open(guide_path, encoding="utf-8") as f:
        content = f.read()

    assert "Render" in content
    assert "Vercel" in content
    assert "Supabase" in content

    # Verify no leaked secret patterns
    secret_patterns = [
        r"eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+",  # JWT token
        r"sbp_[a-zA-Z0-9]{32,}",  # Supabase secret
        r"postgres://[^:]+:[^@]+@",  # Postgres URI with password
    ]
    for pattern in secret_patterns:
        assert not re.search(pattern, content), (
            f"Secret pattern matched in deployment.md: {pattern}"
        )
