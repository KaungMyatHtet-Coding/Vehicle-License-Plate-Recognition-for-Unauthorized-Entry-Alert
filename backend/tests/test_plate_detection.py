"""Focused Day 5 still-image plate-detection tests."""

from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api.routes import recognition
from app.core.config import Settings
from app.main import app
from app.services.detection_contract import PlateDetection
from app.services.plate_detection import (
    DetectedPlate,
    OnnxPlateDetector,
    PlateDetectionError,
    PlateDetectionService,
)

client = TestClient(app)


def image_bytes(size: tuple[int, int] = (160, 80)) -> bytes:
    stream = BytesIO()
    Image.new("RGB", size, color=(20, 40, 60)).save(stream, format="PNG")
    return stream.getvalue()


class FakeDetector:
    """Deterministic detector used without loading model weights."""

    def __init__(self, detections: list[PlateDetection]) -> None:
        self.detections = detections
        self.calls = 0

    def detect(self, image: np.ndarray) -> tuple[list[PlateDetection], float]:
        self.calls += 1
        return self.detections, 1.25


def service_with(detections: list[PlateDetection]) -> PlateDetectionService:
    service = PlateDetectionService(Settings())
    service._detector = FakeDetector(detections)  # type: ignore[assignment]
    return service


@pytest.fixture(autouse=True)
def reset_route_service() -> None:
    recognition._detection_service = None
    yield
    recognition._detection_service = None


def test_import_and_construction_do_not_load_a_model() -> None:
    service = PlateDetectionService(Settings(DETECTOR_MODEL_PATH=None))

    assert service._detector is None


def test_missing_model_configuration_is_structured() -> None:
    service = PlateDetectionService(Settings(DETECTOR_MODEL_PATH=None))

    with pytest.raises(PlateDetectionError) as caught:
        service.detect(image_bytes(), "test-correlation")

    assert caught.value.code == "DETECTOR_MODEL_NOT_CONFIGURED"
    assert caught.value.status_code == 503


def test_missing_model_file_is_structured(tmp_path: Path) -> None:
    service = PlateDetectionService(
        Settings(DETECTOR_MODEL_PATH=tmp_path / "missing.onnx")
    )

    with pytest.raises(PlateDetectionError) as caught:
        service.detect(image_bytes(), "test-correlation")

    assert caught.value.code == "DETECTOR_MODEL_MISSING"


def test_invalid_model_artifact_is_structured(tmp_path: Path) -> None:
    model = tmp_path / "invalid.onnx"
    model.write_bytes(b"not an onnx model")
    service = PlateDetectionService(Settings(DETECTOR_MODEL_PATH=model))

    with pytest.raises(PlateDetectionError) as caught:
        service.detect(image_bytes(), "test-correlation")

    assert caught.value.code == "DETECTOR_MODEL_INVALID"


def test_unloadable_model_is_structured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = tmp_path / "unloadable.onnx"
    model.write_bytes(b"model-shaped-test-data")
    monkeypatch.setattr(
        "app.services.plate_detection.MODEL_SIZE_BYTES", model.stat().st_size
    )
    monkeypatch.setattr(
        "app.services.plate_detection.MODEL_SHA256",
        __import__("hashlib").sha256(model.read_bytes()).hexdigest(),
    )

    def fail_load(*_: Any, **__: Any) -> None:
        raise RuntimeError("private runtime detail")

    monkeypatch.setattr("app.services.plate_detection.ort.InferenceSession", fail_load)

    with pytest.raises(PlateDetectionError) as caught:
        OnnxPlateDetector(model, 0.25, 0.45)

    assert caught.value.code == "DETECTOR_MODEL_UNLOADABLE"
    assert "private runtime detail" not in caught.value.message


def test_model_lifecycle_reuses_one_detector(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[FakeDetector] = []

    def fake_constructor(*_: Any, **__: Any) -> FakeDetector:
        detector = FakeDetector([])
        created.append(detector)
        return detector

    monkeypatch.setattr(
        "app.services.plate_detection.OnnxPlateDetector", fake_constructor
    )
    service = PlateDetectionService(
        Settings(DETECTOR_MODEL_PATH=Path("configured.onnx"))
    )

    service.detect(image_bytes(), "first")
    service.detect(image_bytes(), "second")

    assert len(created) == 1
    assert created[0].calls == 2


def test_zero_detections_return_safe_outcome() -> None:
    result = service_with([]).detect(image_bytes(), "no-plate")

    assert result.status == "no_plate_detected"
    assert result.detection_count == 0
    assert result.detections == []


def test_optional_debug_output_is_isolated_behind_injected_sink() -> None:
    observed: list[tuple[str, tuple[int, ...], int]] = []

    def sink(
        correlation_id: str, image: np.ndarray, plates: list[DetectedPlate]
    ) -> None:
        observed.append((correlation_id, image.shape, len(plates)))

    service = PlateDetectionService(Settings(), debug_sink=sink)
    service._detector = FakeDetector([])  # type: ignore[assignment]

    service.detect(image_bytes(), "debug-correlation")

    assert observed == [("debug-correlation", (80, 160, 3), 0)]


def test_multiple_detections_return_valid_lossless_crops() -> None:
    detections = [
        PlateDetection((10, 15, 90, 45), 0.9, "license_plate"),
        PlateDetection((100, 20, 150, 60), 0.8, "license_plate"),
    ]

    result = service_with(detections).detect(image_bytes(), "multiple")

    assert result.status == "detected"
    assert result.detection_count == 2
    for response, expected in zip(result.detections, detections, strict=True):
        assert tuple(response.bbox.model_dump().values()) == expected.bbox
        decoded = cv2.imdecode(
            np.frombuffer(base64.b64decode(response.crop.base64_data), np.uint8),
            cv2.IMREAD_COLOR,
        )
        assert decoded is not None
        assert decoded.shape[:2] == (
            response.crop.height,
            response.crop.width,
        )


def test_coordinate_mapping_rounds_clips_and_sorts() -> None:
    detector = object.__new__(OnnxPlateDetector)
    detector._confidence_threshold = 0.25
    detector._nms_iou_threshold = 0.45

    class FakeSession:
        def run(self, *_: Any, **__: Any) -> list[np.ndarray]:
            output = np.zeros((1, 5, 8400), dtype=np.float32)
            # On a 320x160 image, scale=2 and vertical padding=160.
            output[0, :, 0] = [620, 470, 80, 60, 0.7]
            output[0, :, 1] = [200, 260, 120, 80, 0.9]
            return [output]

    detector._session = FakeSession()
    image = np.zeros((160, 320, 3), dtype=np.uint8)

    detections, inference_ms = detector.detect(image)

    assert inference_ms >= 0
    assert [item.confidence for item in detections] == pytest.approx([0.9, 0.7])
    assert detections[0].bbox == (70, 30, 130, 70)
    assert detections[1].bbox == (290, 140, 320, 160)


def test_detection_api_returns_zero_plate_contract() -> None:
    recognition._detection_service = service_with([])

    response = client.post(
        "/api/recognition/detect-plates",
        files={"file": ("vehicle.png", image_bytes(), "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    UUID(body["correlation_id"])
    assert body["status"] == "no_plate_detected"
    assert body["detection_count"] == 0
    assert body["detections"] == []


def test_detection_api_preserves_secure_validation() -> None:
    recognition._detection_service = service_with([])

    response = client.post(
        "/api/recognition/detect-plates",
        files={"file": ("vehicle.jpg", b"not an image", "image/jpeg")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IMAGE_CONTENT_INVALID"


def test_detection_api_reports_missing_model_without_internal_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recognition._detection_service = PlateDetectionService(
        Settings(DETECTOR_MODEL_PATH=None)
    )

    response = client.post(
        "/api/recognition/detect-plates",
        files={"file": ("vehicle.png", image_bytes(), "image/png")},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "DETECTOR_MODEL_NOT_CONFIGURED"
    assert "D:\\" not in body["error"]["message"]
    UUID(body["error"]["correlation_id"])


def test_selected_model_returns_valid_fixture_boxes_and_crops() -> None:
    repository = Path(__file__).resolve().parents[2]
    model_path = repository / "models" / "day4" / "best.onnx"
    if not model_path.is_file():
        pytest.skip("ignored locally verified Day 4 model is unavailable")

    ground_truth = json.loads(
        (repository / "sample-data" / "evaluation" / "ground_truth.json").read_text(
            encoding="utf-8"
        )
    )
    service = PlateDetectionService(Settings(DETECTOR_MODEL_PATH=model_path))

    for fixture in ground_truth:
        data = (
            repository / "sample-data" / "evaluation" / fixture["file"]
        ).read_bytes()
        result = service.detect(data, fixture["file"])
        assert result.detection_count == fixture["expected_detections"]
        assert len(result.detections) == fixture["expected_detections"]
        for detection in result.detections:
            box = detection.bbox
            assert 0 <= box.x1 < box.x2 <= result.image_width
            assert 0 <= box.y1 < box.y2 <= result.image_height
            assert detection.crop.width == box.x2 - box.x1
            assert detection.crop.height == box.y2 - box.y1
    assert service._detector is not None
