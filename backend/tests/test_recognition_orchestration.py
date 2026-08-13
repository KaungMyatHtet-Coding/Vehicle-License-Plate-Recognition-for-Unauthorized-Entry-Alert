"""Deterministic Day 13 orchestration and HTTP contract tests."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from io import BytesIO
from uuid import UUID

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api.routes.recognition import get_orchestration_service
from app.main import app
from app.schemas.decision import EntryDecision
from app.schemas.detection import (
    BoundingBox,
    ImageDetectionResponse,
    PlateCropResponse,
    PlateDetectionResponse,
)
from app.schemas.logging import (
    DecisionAuditSnapshot,
    DetectionLoggingResult,
    EvidenceReference,
)
from app.schemas.ocr import PlateOcrResponse
from app.services.plate_detection import PlateDetectionError
from app.services.recognition_orchestration import RecognitionOrchestrationService

client = TestClient(app)
CORRELATION_ID = "11111111-1111-4111-8111-111111111111"
VEHICLE_ID = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 8, 4, 9, 0, tzinfo=timezone.utc)


def image_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (96, 64), "white").save(stream, "JPEG")
    return stream.getvalue()


def crop_base64() -> str:
    ok, encoded = cv2.imencode(".png", np.full((20, 60, 3), 255, np.uint8))
    assert ok
    return base64.b64encode(encoded).decode("ascii")


def detection(with_plate: bool = True) -> ImageDetectionResponse:
    plates = (
        [
            PlateDetectionResponse(
                bbox=BoundingBox(x1=10, y1=20, x2=70, y2=40),
                confidence=0.91,
                label="license_plate",
                crop=PlateCropResponse(
                    media_type="image/png",
                    base64_data=crop_base64(),
                    width=60,
                    height=20,
                ),
            )
        ]
        if with_plate
        else []
    )
    return ImageDetectionResponse(
        correlation_id=CORRELATION_ID,
        status="detected" if with_plate else "no_plate_detected",
        detection_count=len(plates),
        image_width=96,
        image_height=64,
        inference_ms=1.0,
        total_ms=2.0,
        detections=plates,
    )


def ocr() -> PlateOcrResponse:
    return PlateOcrResponse(
        correlation_id=CORRELATION_ID,
        status="recognized",
        review_reason=None,
        raw_text="ABC 123",
        normalized_text="ABC123",
        confidence=0.94,
        mode="recognition_only",
        inference_ms=3.0,
        total_ms=4.0,
        image_width=60,
        image_height=20,
    )


def decision() -> EntryDecision:
    return EntryDecision(
        correlation_id=CORRELATION_ID,
        decision="AUTHORIZED",
        reason="ACTIVE_MATCH",
        message="The vehicle record permits entry at this time.",
        normalized_plate="ABC123",
        confidence=0.94,
        vehicle_id=VEHICLE_ID,
        evaluated_at=NOW,
    )


def logging() -> DetectionLoggingResult:
    return DetectionLoggingResult(
        decision=DecisionAuditSnapshot.from_entry_decision(decision()),
        status="completed",
        failures=(),
        log_persisted=True,
        evidence=EvidenceReference(
            bucket="detection-evidence", object_path="2026/08/04/evidence.jpg"
        ),
        signed_access=None,
        completed_at=NOW,
    )


class FakeDetector:
    def __init__(self, result: ImageDetectionResponse) -> None:
        self.result = result

    def detect(self, _: bytes, correlation_id: str) -> ImageDetectionResponse:
        return self.result.model_copy(update={"correlation_id": correlation_id})


class FakeOcr:
    calls = 0

    def recognize(self, _: bytes, correlation_id: str) -> PlateOcrResponse:
        self.calls += 1
        return ocr().model_copy(update={"correlation_id": correlation_id})


class FakeDecision:
    def decide(self, value: PlateOcrResponse) -> EntryDecision:
        return decision().model_copy(update={"correlation_id": value.correlation_id})


class FakeLogging:
    def persist(self, **values: object) -> DetectionLoggingResult:
        supplied = values["decision"]
        assert isinstance(supplied, EntryDecision)
        return logging().model_copy(
            update={"decision": DecisionAuditSnapshot.from_entry_decision(supplied)}
        )


def service(with_plate: bool = True) -> RecognitionOrchestrationService:
    return RecognitionOrchestrationService(
        FakeDetector(detection(with_plate)),  # type: ignore[arg-type]
        FakeOcr(),  # type: ignore[arg-type]
        FakeDecision(),  # type: ignore[arg-type]
        FakeLogging(),  # type: ignore[arg-type]
    )


@pytest.fixture(autouse=True)
def clear_overrides() -> None:
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_orchestration_preserves_authoritative_decision_and_evidence() -> None:
    result = service().recognize(image_bytes(), CORRELATION_ID)

    assert result.status == "completed"
    assert result.logging is not None
    assert result.logging.decision.decision == "AUTHORIZED"
    assert result.logging.decision.reason == "ACTIVE_MATCH"
    assert result.ocr is not None and result.ocr.normalized_text == "ABC123"
    assert result.selected_plate is not None
    assert result.timings.detection_ms == 2.0


def test_ocr_crop_padding_is_bounded_and_preserves_public_bbox() -> None:
    source = np.zeros((64, 96, 3), dtype=np.uint8)
    candidate = detection().detections[0]

    encoded = RecognitionOrchestrationService._ocr_crop_bytes(candidate, source)
    decoded = cv2.imdecode(np.frombuffer(encoded, dtype=np.uint8), cv2.IMREAD_COLOR)

    assert decoded is not None
    assert decoded.shape[:2] == (60, 96)
    assert candidate.bbox.model_dump() == {
        "x1": 10,
        "y1": 20,
        "x2": 70,
        "y2": 40,
    }


def test_no_plate_stops_before_ocr_decision_and_logging() -> None:
    fake_ocr = FakeOcr()
    orchestrator = RecognitionOrchestrationService(
        FakeDetector(detection(False)),  # type: ignore[arg-type]
        fake_ocr,  # type: ignore[arg-type]
        FakeDecision(),  # type: ignore[arg-type]
        FakeLogging(),  # type: ignore[arg-type]
    )

    result = orchestrator.recognize(image_bytes(), CORRELATION_ID)

    assert result.status == "no_plate_detected"
    assert result.selected_plate is None
    assert result.ocr is None
    assert result.logging is None
    assert fake_ocr.calls == 0


def test_analyze_endpoint_returns_runtime_contract() -> None:
    app.dependency_overrides[get_orchestration_service] = service

    response = client.post(
        "/api/recognition/analyze",
        files={"file": ("vehicle.jpg", image_bytes(), "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["logging"]["decision"]["decision"] == "AUTHORIZED"
    assert body["correlation_id"] == body["ocr"]["correlation_id"]
    assert body["selected_plate"]["crop"]["media_type"] == "image/png"


def test_analyze_endpoint_preserves_secure_image_rejection() -> None:
    app.dependency_overrides[get_orchestration_service] = service

    response = client.post(
        "/api/recognition/analyze",
        files={"file": ("vehicle.txt", b"not-image", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "IMAGE_EXTENSION_UNSUPPORTED"
    assert response.json()["error"]["correlation_id"]


def test_analyze_endpoint_sanitizes_expected_and_unexpected_failures() -> None:
    class FailureService:
        def recognize(self, _: bytes, __: str) -> object:
            raise PlateDetectionError(
                "DETECTOR_INFERENCE_FAILED", "Plate detection could not be completed."
            )

    app.dependency_overrides[get_orchestration_service] = FailureService
    expected = client.post(
        "/api/recognition/analyze",
        files={"file": ("vehicle.jpg", image_bytes(), "image/jpeg")},
    )
    assert expected.status_code == 503
    assert expected.json()["error"]["code"] == "DETECTOR_INFERENCE_FAILED"

    class UnexpectedFailureService:
        def recognize(self, _: bytes, __: str) -> object:
            raise RuntimeError("provider diagnostic detail")

    app.dependency_overrides[get_orchestration_service] = UnexpectedFailureService
    unexpected = client.post(
        "/api/recognition/analyze",
        files={"file": ("vehicle.jpg", image_bytes(), "image/jpeg")},
    )
    assert unexpected.status_code == 500
    assert unexpected.json()["error"]["code"] == "RECOGNITION_FAILED"
    assert "diagnostic" not in unexpected.text


def test_cors_preflight_allows_frontend_post_without_credentials() -> None:
    response = client.options(
        "/api/recognition/analyze",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "POST" in response.headers["access-control-allow-methods"]
    assert response.headers.get("access-control-allow-credentials") != "true"
