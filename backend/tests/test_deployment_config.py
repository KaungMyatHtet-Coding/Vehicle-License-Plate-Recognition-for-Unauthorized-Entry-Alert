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
    assert "ENV DETECTOR_MODEL_PATH=/app/models/day4/best.onnx" in content
    assert "backend/pyproject.toml" not in content
    assert content.count("pip install --no-cache-dir") == 1
    assert "pip install --no-cache-dir -r /app/requirements.txt" in content
    assert "127.0.0.1:8000:8000" in content
    assert "COPY models/day4/best.onnx /app/models/day4/best.onnx" in content
    assert content.count("/app/models/day4/best.onnx") >= 4
    assert "stat -c '%s' /app/models/day4/best.onnx" in content
    assert "sha256sum /app/models/day4/best.onnx" in content
    assert "ENV PORT=8000" in content
    assert "${PORT}" in content
    assert "curl -f http://localhost:${PORT}/health" in content
    assert "apt-get install" in content and "curl" in content
    assert "12265233" in content
    assert "a599289e5c25ab693fd7c6a152093f95fc34aef9b59b2c798127173e6e7ba2d9" in content


def test_production_requirements_declare_direct_runtime_dependencies() -> None:
    requirements_path = os.path.join(_ROOT, "backend", "requirements.txt")
    with open(requirements_path, encoding="utf-8") as f:
        lines = {line.strip().split("==", 1)[0].lower() for line in f if line.strip()}

    expected = {
        "fastapi",
        "pydantic",
        "pydantic-settings",
        "starlette",
        "uvicorn[standard]",
        "pillow",
        "python-multipart",
        "numpy",
        "opencv-python-headless",
        "onnxruntime",
        "rapidocr",
        "supabase",
        "postgrest",
    }
    assert expected <= lines
    assert all("-e " not in line for line in lines)
    assert all("git+" not in line for line in lines)
    assert all("*" not in line for line in lines)
    assert all("/" not in line for line in lines)


def test_model_prerequisite_and_local_only_boundary_are_documented() -> None:
    readme_path = os.path.join(_ROOT, "backend", "README.md")
    deployment_path = os.path.join(_ROOT, "docs", "deployment.md")
    render_path = os.path.join(_ROOT, "render.yaml")
    with open(readme_path, encoding="utf-8") as f:
        readme = f.read()
    with open(deployment_path, encoding="utf-8") as f:
        deployment = f.read()
    with open(render_path, encoding="utf-8") as f:
        render = f.read()

    for content in (readme, deployment):
        assert "models/day4/best.onnx" in content
        assert "12,265,233" in content
        assert (
            "a599289e5c25ab693fd7c6a152093f95fc34aef9b59b2c798127173e6e7ba2d9"
            in content
        )
        assert "127.0.0.1:8000:8000" in content
        assert "deferred" in content.lower()
        assert "license" in content.lower()
        assert "attribution" in content.lower()
        assert (
            "docker build --file backend/Dockerfile --tag cvpx-local:phase3 ."
            in content
        )
        assert (
            "docker run --rm --publish 127.0.0.1:8000:8000 cvpx-local:phase3" in content
        )
    assert "services:" not in render
    assert "unsupported" in render.lower()


def test_container_path_and_healthcheck_are_model_independent() -> None:
    dockerfile_path = os.path.join(_ROOT, "backend", "Dockerfile")
    health_path = os.path.join(_ROOT, "backend", "app", "api", "routes", "health.py")
    with open(dockerfile_path, encoding="utf-8") as f:
        dockerfile = f.read()
    with open(health_path, encoding="utf-8") as f:
        health = f.read()

    copy_line = "COPY models/day4/best.onnx /app/models/day4/best.onnx"
    configured_path = "ENV DETECTOR_MODEL_PATH=/app/models/day4/best.onnx"
    assert copy_line in dockerfile
    assert configured_path in dockerfile
    assert "/app/models/day4/best.onnx" in dockerfile.split(copy_line, 1)[1]
    assert "PlateDetectionService" not in health
    assert "OnnxPlateDetector" not in health
    assert "create_client" not in health
    assert "get_application_dependencies" not in health


def test_clean_container_opencv_limitation_is_explicit() -> None:
    readme_path = os.path.join(_ROOT, "backend", "README.md")
    with open(readme_path, encoding="utf-8") as f:
        content = f.read().lower()

    assert "opencv-python==5.0.0.93" in content
    assert "opencv-python-headless==4.12.0.88" in content
    assert "unverified" in content


def test_frontend_api_variable_and_public_deployment_claims_are_safe() -> None:
    root_env_path = os.path.join(_ROOT, ".env.example")
    frontend_env_path = os.path.join(_ROOT, "frontend", ".env.example")
    deployment_path = os.path.join(_ROOT, "docs", "deployment.md")
    with open(root_env_path, encoding="utf-8") as f:
        root_env = f.read()
    with open(frontend_env_path, encoding="utf-8") as f:
        frontend_env = f.read()
    with open(deployment_path, encoding="utf-8") as f:
        deployment = f.read()

    assert "NEXT_PUBLIC_API_BASE_URL" in root_env
    assert "NEXT_PUBLIC_API_BASE_URL" in frontend_env
    assert "NEXT_PUBLIC_API_URL" not in deployment
    assert "public deployment success" in deployment.lower()


def test_render_yaml_is_explicitly_deferred() -> None:
    """render.yaml cannot be mistaken for verified public deployment config."""
    render_yaml_path = os.path.join(_ROOT, "render.yaml")
    assert os.path.isfile(render_yaml_path), "render.yaml must exist"

    with open(render_yaml_path, encoding="utf-8") as f:
        content = f.read()

    assert "services:" not in content
    assert "unsupported" in content.lower()


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
