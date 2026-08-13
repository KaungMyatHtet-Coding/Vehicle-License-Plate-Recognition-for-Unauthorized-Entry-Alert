"""Focused Day 8 tests for lazy local OCR and conservative normalization."""

from __future__ import annotations

import math
import sys
import threading
import time
from io import BytesIO
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api.routes import recognition
from app.core.config import Settings
from app.main import app
from app.schemas.ocr import PlateOcrResponse
from app.services.ocr_recognition import (
    EngineOcrResult,
    PlateOcrError,
    PlateOcrService,
    RapidOcrCpuEngine,
    normalize_plate_text,
)

client = TestClient(app)


def image_bytes(size: tuple[int, int] = (160, 80)) -> bytes:
    stream = BytesIO()
    Image.new("RGB", size, color=(245, 245, 245)).save(stream, format="PNG")
    return stream.getvalue()


class FakeEngine:
    def __init__(self, results: list[EngineOcrResult]) -> None:
        self.results = results
        self.modes: list[str] = []

    def recognize(self, image: np.ndarray, mode: str) -> EngineOcrResult:
        assert image.dtype == np.uint8
        self.modes.append(mode)
        return self.results.pop(0)


def service_with(
    results: list[EngineOcrResult], **settings: Any
) -> tuple[PlateOcrService, FakeEngine]:
    service = PlateOcrService(Settings(**settings))
    engine = FakeEngine(results)
    service._engine = engine  # type: ignore[assignment]
    return service, engine


@pytest.fixture(autouse=True)
def reset_route_services() -> None:
    recognition._detection_service = None
    recognition._ocr_service = None
    yield
    recognition._detection_service = None
    recognition._ocr_service = None


@pytest.mark.parametrize(
    ("raw_text", "expected"),
    [
        ("YGN 5A-1234", "YGN5A1234"),
        ("  ygn_5a / 1234  ", "YGN5A1234"),
        ("ABC.O0-19", "ABCO019"),
        ("ရက 12-é", "12"),
        ("", ""),
    ],
)
def test_normalization_is_separate_conservative_and_deterministic(
    raw_text: str, expected: str
) -> None:
    assert normalize_plate_text(raw_text) == expected


def test_normalization_does_not_substitute_letter_o_and_digit_zero() -> None:
    assert normalize_plate_text("O0 0O") == "O00O"


def test_ocr_settings_have_safe_defaults_and_bounds() -> None:
    settings = Settings()

    assert settings.ocr_min_confidence == 0.80
    assert settings.ocr_full_pipeline_fallback is True
    with pytest.raises(ValueError):
        Settings(OCR_MIN_CONFIDENCE=-0.01)
    with pytest.raises(ValueError):
        Settings(OCR_MIN_CONFIDENCE=1.01)
    with pytest.raises(ValueError):
        Settings(OCR_FULL_PIPELINE_FALLBACK="not-a-boolean")


def test_service_construction_and_application_import_are_lazy() -> None:
    service = PlateOcrService(Settings())

    assert service._engine is None
    assert "rapidocr" not in sys.modules


def test_reliable_primary_returns_raw_normalized_text_and_confidence() -> None:
    service, engine = service_with(
        [EngineOcrResult("YGN 5A-1234", 0.95, 2.5, "recognition_only")]
    )

    result = service.recognize(image_bytes(), "correlation")

    assert result.status == "recognized"
    assert result.review_reason is None
    assert result.raw_text == "YGN 5A-1234"
    assert result.normalized_text == "YGN5A1234"
    assert result.confidence == 0.95
    assert result.mode == "recognition_only"
    assert engine.modes == ["recognition_only"]


def test_region_and_body_on_separate_ocr_lines_are_reconstructed() -> None:
    service, _ = service_with(
        [EngineOcrResult("MDY\n5D-3062", 0.96, 2.5, "recognition_only")]
    )

    result = service.recognize(image_bytes(), "correlation")

    assert result.status == "recognized"
    assert result.normalized_text == "MDY5D3062"
    assert result.raw_text == "MDY\n5D-3062"


def test_empty_primary_uses_day7_full_pipeline_fallback() -> None:
    service, engine = service_with(
        [
            EngineOcrResult("", None, 1.0, "recognition_only"),
            EngineOcrResult("MDY 3B-5678", 0.93, 4.0, "full_pipeline"),
        ]
    )

    result = service.recognize(image_bytes(), "correlation")

    assert result.status == "recognized"
    assert result.normalized_text == "MDY3B5678"
    assert result.mode == "full_pipeline"
    assert engine.modes == ["recognition_only", "full_pipeline"]


def test_empty_output_is_flagged_for_manual_review() -> None:
    service, _ = service_with(
        [
            EngineOcrResult("", None, 1.0, "recognition_only"),
            EngineOcrResult(" -- ", 0.99, 2.0, "full_pipeline"),
        ]
    )

    result = service.recognize(image_bytes(), "correlation")

    assert result.status == "manual_review"
    assert result.review_reason == "OCR_EMPTY"
    assert result.normalized_text == ""


def test_low_confidence_is_flagged_without_authorization_semantics() -> None:
    service, _ = service_with(
        [
            EngineOcrResult("ABC 123", 0.20, 1.0, "recognition_only"),
            EngineOcrResult("ABC 123", 0.30, 2.0, "full_pipeline"),
        ],
        OCR_MIN_CONFIDENCE=0.80,
    )

    result = service.recognize(image_bytes(), "correlation")

    assert result.status == "manual_review"
    assert result.review_reason == "OCR_LOW_CONFIDENCE"
    assert result.normalized_text == "ABC123"
    assert "authorized" not in result.model_dump()
    assert "unauthorized" not in result.model_dump()


@pytest.mark.parametrize(
    ("confidence", "expected_status"),
    [
        (0.799999, "manual_review"),
        (0.80, "recognized"),
        (0.800001, "recognized"),
    ],
)
def test_confidence_threshold_boundary(confidence: float, expected_status: str) -> None:
    service, _ = service_with(
        [EngineOcrResult("ABC123", confidence, 1.0, "recognition_only")],
        OCR_MIN_CONFIDENCE=0.80,
        OCR_FULL_PIPELINE_FALLBACK=False,
    )

    result = service.recognize(image_bytes(), "correlation")

    assert result.status == expected_status
    assert result.review_reason == (
        "OCR_LOW_CONFIDENCE" if expected_status == "manual_review" else None
    )


def test_invalid_engine_output_is_structured() -> None:
    service, _ = service_with(
        [EngineOcrResult("ABC123", math.nan, 1.0, "recognition_only")]
    )

    with pytest.raises(PlateOcrError) as caught:
        service.recognize(image_bytes(), "correlation")

    assert caught.value.code == "OCR_OUTPUT_INVALID"


def test_engine_output_mode_must_match_requested_mode() -> None:
    service, _ = service_with([EngineOcrResult("ABC123", 0.95, 1.0, "full_pipeline")])

    with pytest.raises(PlateOcrError) as caught:
        service.recognize(image_bytes(), "correlation")

    assert caught.value.code == "OCR_OUTPUT_INVALID"


def test_fallback_can_be_disabled_by_environment_setting() -> None:
    service, engine = service_with(
        [EngineOcrResult("ABC 123", 0.20, 1.0, "recognition_only")],
        OCR_FULL_PIPELINE_FALLBACK=False,
    )

    result = service.recognize(image_bytes(), "correlation")

    assert result.status == "manual_review"
    assert result.mode == "recognition_only"
    assert engine.modes == ["recognition_only"]


def test_service_reuses_one_lazy_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[FakeEngine] = []

    def constructor() -> FakeEngine:
        engine = FakeEngine(
            [
                EngineOcrResult("ABC123", 0.9, 1.0, "recognition_only"),
                EngineOcrResult("ABC123", 0.9, 1.0, "recognition_only"),
            ]
        )
        created.append(engine)
        return engine

    monkeypatch.setattr("app.services.ocr_recognition.RapidOcrCpuEngine", constructor)
    service = PlateOcrService(Settings())

    service.recognize(image_bytes(), "first")
    service.recognize(image_bytes(), "second")

    assert len(created) == 1
    assert created[0].modes == ["recognition_only", "recognition_only"]


def test_concurrent_initialization_creates_exactly_one_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[FakeEngine] = []
    barrier = threading.Barrier(3)

    def constructor() -> FakeEngine:
        time.sleep(0.02)
        engine = FakeEngine([])
        created.append(engine)
        return engine

    monkeypatch.setattr("app.services.ocr_recognition.RapidOcrCpuEngine", constructor)
    service = PlateOcrService(Settings())
    engines: list[object] = []

    def load_engine() -> None:
        barrier.wait()
        engines.append(service._get_engine())

    threads = [threading.Thread(target=load_engine) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert len(created) == 1
    assert engines == [created[0], created[0]]


def test_cpu_provider_is_enforced_for_every_ocr_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Session:
        def __init__(self, providers: list[str]) -> None:
            self.session = SimpleNamespace(get_providers=lambda: providers)

    class FakeRapidOcr:
        def __init__(self) -> None:
            self.text_det = SimpleNamespace(session=Session(["CPUExecutionProvider"]))
            self.text_cls = SimpleNamespace(session=Session(["CUDAExecutionProvider"]))
            self.text_rec = SimpleNamespace(session=Session(["CPUExecutionProvider"]))

    monkeypatch.setitem(sys.modules, "rapidocr", SimpleNamespace(RapidOCR=FakeRapidOcr))
    monkeypatch.setattr(
        "app.services.ocr_recognition.importlib.metadata.version",
        lambda _: "3.9.2",
    )

    with pytest.raises(PlateOcrError) as caught:
        RapidOcrCpuEngine()

    assert caught.value.code == "OCR_PROVIDER_INVALID"


def test_runtime_failure_is_structured_without_internal_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenRapidOcr:
        def __init__(self) -> None:
            raise RuntimeError("C:\\private\\models\\secret.onnx")

    monkeypatch.setitem(
        sys.modules, "rapidocr", SimpleNamespace(RapidOCR=BrokenRapidOcr)
    )
    monkeypatch.setattr(
        "app.services.ocr_recognition.importlib.metadata.version",
        lambda _: "3.9.2",
    )

    with pytest.raises(PlateOcrError) as caught:
        RapidOcrCpuEngine()

    assert caught.value.code == "OCR_RUNTIME_UNLOADABLE"
    assert "C:\\" not in caught.value.message
    assert "secret.onnx" not in caught.value.message


def test_incompatible_runtime_version_is_structured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.ocr_recognition.importlib.metadata.version",
        lambda _: "4.0.0",
    )

    with pytest.raises(PlateOcrError) as caught:
        RapidOcrCpuEngine()

    assert caught.value.code == "OCR_VERSION_INVALID"


def test_inference_failure_is_structured_without_raw_exception() -> None:
    class FailingRapidOcr:
        def __call__(self, *_: object, **__: object) -> object:
            raise RuntimeError("D:\\private\\ocr-model.onnx")

    engine = RapidOcrCpuEngine.__new__(RapidOcrCpuEngine)
    engine._engine = FailingRapidOcr()  # type: ignore[assignment]

    with pytest.raises(PlateOcrError) as caught:
        engine.recognize(np.zeros((20, 80, 3), dtype=np.uint8), "recognition_only")

    assert caught.value.code == "OCR_INFERENCE_FAILED"
    assert "D:\\" not in caught.value.message


class FakeApiService:
    def recognize(self, _: bytes, correlation_id: str) -> PlateOcrResponse:
        return PlateOcrResponse(
            correlation_id=correlation_id,
            status="recognized",
            review_reason=None,
            raw_text="YGN 5A-1234",
            normalized_text="YGN5A1234",
            confidence=0.95,
            mode="recognition_only",
            inference_ms=1.0,
            total_ms=2.0,
            image_width=160,
            image_height=80,
        )


def test_ocr_api_returns_transient_text_contract() -> None:
    recognition._ocr_service = FakeApiService()  # type: ignore[assignment]

    response = client.post(
        "/api/recognition/recognize-plate",
        files={"file": ("plate.png", image_bytes(), "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    UUID(body["correlation_id"])
    assert body["status"] == "recognized"
    assert body["raw_text"] == "YGN 5A-1234"
    assert body["normalized_text"] == "YGN5A1234"
    assert body["confidence"] == 0.95


def test_ocr_api_preserves_secure_image_validation() -> None:
    recognition._ocr_service = FakeApiService()  # type: ignore[assignment]

    response = client.post(
        "/api/recognition/recognize-plate",
        files={"file": ("plate.jpg", b"not an image", "image/jpeg")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IMAGE_CONTENT_INVALID"


def test_ocr_api_reports_safe_structured_runtime_failure() -> None:
    class FailingService:
        def recognize(self, _: bytes, __: str) -> PlateOcrResponse:
            raise PlateOcrError(
                "OCR_RUNTIME_MISSING", "The local OCR runtime is not available."
            )

    recognition._ocr_service = FailingService()  # type: ignore[assignment]

    response = client.post(
        "/api/recognition/recognize-plate",
        files={"file": ("plate.png", image_bytes(), "image/png")},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "OCR_RUNTIME_MISSING"
    assert "D:\\" not in body["error"]["message"]
    UUID(body["error"]["correlation_id"])
