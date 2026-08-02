"""Day 21 tests for online QA, security hardening, secret scanning, and error sanitization."""

from __future__ import annotations

import os
import re

from fastapi.testclient import TestClient

from app.main import app

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

client = TestClient(app)


def test_health_endpoint_response_format() -> None:
    """GET /health returns 200 with sanitized status without leaking internal paths."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "service" in data
    assert "version" in data
    # Ensure no internal path leaks
    assert "D:\\" not in str(data)
    assert "/home/" not in str(data)


def test_cors_preflight_headers() -> None:
    """OPTIONS request returns valid CORS headers for allowed origin."""
    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
    }
    response = client.options("/api/recognition/analyze", headers=headers)
    # FastAPI returns 200 for allowed preflight CORS
    assert response.status_code in (200, 204)
    assert (
        response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    )


def test_upload_oversized_image_returns_sanitized_error() -> None:
    """POST /api/recognition/analyze with oversized payload (>10MB) fails gracefully with 400/413."""
    # Create 11 MB dummy bytes
    oversized_bytes = b"0" * (11 * 1024 * 1024)
    response = client.post(
        "/api/recognition/analyze",
        files={"file": ("large.jpg", oversized_bytes, "image/jpeg")},
    )
    assert response.status_code in (400, 413, 422)
    data = response.json()
    assert "error" in data or "detail" in data
    # Ensure error message does not leak server stack traces
    assert "Traceback" not in str(data)


def test_invalid_endpoint_returns_sanitized_404() -> None:
    """Non-existent API endpoint returns standard 404 without tracebacks."""
    response = client.get("/api/nonexistent-endpoint-12345")
    assert response.status_code == 404
    data = response.json()
    assert "Traceback" not in str(data)


def test_repository_secret_scanner() -> None:
    """Repository code and docs must contain no hardcoded passwords, tokens, or private keys."""
    secret_patterns = [
        (re.compile(r"sbp_[a-zA-Z0-9]{32,}"), "Supabase Service Key"),
        (re.compile(r"-----BEGIN (RSA|EC|PRIVATE) KEY-----"), "Private Key"),
        (
            re.compile(
                r"postgres://[a-zA-Z0-9_]+:[a-zA-Z0-9_]+@[a-zA-Z0-9.-]+:[0-9]+/[a-zA-Z0-9_]+"
            ),
            "Database Password in Connection String",
        ),
    ]

    scanned_extensions = (".py", ".ts", ".tsx", ".md", ".json", ".yaml", ".yml")
    forbidden_files = (".env.production", "secrets.json")

    # Ensure forbidden secret files do not exist
    for f_name in forbidden_files:
        assert not os.path.exists(os.path.join(_ROOT, f_name)), (
            f"Forbidden secret file exists: {f_name}"
        )

    # Scan codebase files
    for root, dirs, files in os.walk(_ROOT):
        # Skip virtualenvs, node_modules, and git
        dirs[:] = [
            d for d in dirs if d not in (".venv", "node_modules", ".git", ".next")
        ]

        for file_name in files:
            if (
                file_name.endswith(scanned_extensions)
                and not file_name.startswith(".env")
                and not file_name.startswith("test_")
            ):
                file_path = os.path.join(root, file_name)
                try:
                    with open(file_path, encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    for pattern, description in secret_patterns:
                        match = pattern.search(content)
                        assert not match, (
                            f"Secret pattern '{description}' found in {file_path}"
                        )
                except OSError:
                    continue
