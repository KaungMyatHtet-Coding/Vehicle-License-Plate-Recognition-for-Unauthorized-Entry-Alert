"""Day 3 tests for transient image-input validation."""

from io import BytesIO
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import get_settings
from app.main import app

client = TestClient(app)


def image_bytes(image_format: str = "JPEG", size: tuple[int, int] = (64, 48)) -> bytes:
    stream = BytesIO()
    Image.new("RGB", size, color=(12, 34, 56)).save(stream, format=image_format)
    return stream.getvalue()


@pytest.mark.parametrize(
    ("filename", "content_type", "image_format"),
    [("vehicle.jpg", "image/jpeg", "JPEG"), ("vehicle.png", "image/png", "PNG")],
)
def test_supported_images_return_validation_metadata(
    filename: str, content_type: str, image_format: str
) -> None:
    data = image_bytes(image_format)
    response = client.post(
        "/api/recognition/validate-image",
        files={"file": (filename, data, content_type)},
    )

    assert response.status_code == 200
    body = response.json()
    UUID(body["correlation_id"])
    assert body["filename"] == filename
    assert body["content_type"] == content_type
    assert body["detected_format"] == image_format
    assert body["size_bytes"] == len(data)
    assert body["width"] == 64
    assert body["height"] == 48


def test_missing_file_is_rejected_with_structured_error() -> None:
    response = client.post("/api/recognition/validate-image")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IMAGE_FILE_REQUIRED"
    UUID(response.json()["error"]["correlation_id"])


def test_empty_file_is_rejected() -> None:
    response = client.post(
        "/api/recognition/validate-image",
        files={"file": ("empty.jpg", b"", "image/jpeg")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IMAGE_EMPTY"


def test_unsupported_extension_is_rejected() -> None:
    response = client.post(
        "/api/recognition/validate-image",
        files={"file": ("vehicle.gif", image_bytes(), "image/gif")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "IMAGE_EXTENSION_UNSUPPORTED"


def test_spoofed_content_is_rejected() -> None:
    response = client.post(
        "/api/recognition/validate-image",
        files={"file": ("vehicle.jpg", b"not an image", "image/jpeg")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IMAGE_CONTENT_INVALID"


def test_mismatched_mime_and_decoded_format_is_rejected() -> None:
    response = client.post(
        "/api/recognition/validate-image",
        files={"file": ("vehicle.jpg", image_bytes("PNG"), "image/jpeg")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "IMAGE_CONTENT_MISMATCH"


def test_truncated_image_is_rejected() -> None:
    response = client.post(
        "/api/recognition/validate-image",
        files={"file": ("vehicle.jpg", image_bytes()[:-20], "image/jpeg")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IMAGE_CONTENT_INVALID"


def test_oversized_image_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "max_image_bytes", 100)
    response = client.post(
        "/api/recognition/validate-image",
        files={"file": ("vehicle.jpg", image_bytes(), "image/jpeg")},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "IMAGE_TOO_LARGE"


def test_dimensions_outside_limits_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "min_image_width", 64)
    response = client.post(
        "/api/recognition/validate-image",
        files={"file": ("small.jpg", image_bytes(size=(32, 48)), "image/jpeg")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "IMAGE_DIMENSIONS_UNSUPPORTED"
