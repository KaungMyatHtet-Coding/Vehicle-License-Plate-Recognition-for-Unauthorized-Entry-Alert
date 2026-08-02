"""Day 16 end-to-end core system integration and fail-closed security tests."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from io import BytesIO

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api.routes.recognition import get_orchestration_service
from app.dependencies import get_application_dependencies
from app.main import app
from app.schemas.detection import (
    BoundingBox,
    ImageDetectionResponse,
    PlateCropResponse,
    PlateDetectionResponse,
)
from app.schemas.ocr import PlateOcrResponse
from app.schemas.vehicles import VehicleCreate
from app.services.authorization_decision import AuthorizationDecisionService
from app.services.detection_logging import DetectionLoggingService
from app.services.evidence_storage import EvidenceStorageError
from app.services.recognition_orchestration import RecognitionOrchestrationService
from app.services.vehicle_management import VehicleManagementService

client = TestClient(app)
NOW = datetime(2026, 8, 7, 10, 0, 0, tzinfo=timezone.utc)


def valid_jpeg_bytes(width: int = 200, height: int = 150) -> bytes:
    stream = BytesIO()
    Image.new("RGB", (width, height), "blue").save(stream, "JPEG")
    return stream.getvalue()


def valid_crop_base64() -> str:
    ok, encoded = cv2.imencode(".png", np.full((30, 80, 3), 200, np.uint8))
    assert ok
    return base64.b64encode(encoded).decode("ascii")


class MockDetector:
    def __init__(self, with_plate: bool = True, detection_count: int = 1) -> None:
        self.with_plate = with_plate
        self.detection_count = detection_count

    def detect(self, image_bytes: bytes, correlation_id: str) -> ImageDetectionResponse:
        if not self.with_plate:
            return ImageDetectionResponse(
                correlation_id=correlation_id,
                status="no_plate_detected",
                detection_count=0,
                image_width=200,
                image_height=150,
                inference_ms=12.5,
                total_ms=15.0,
                detections=[],
            )
        detections = []
        for i in range(self.detection_count):
            detections.append(
                PlateDetectionResponse(
                    bbox=BoundingBox(x1=10 + i * 10, y1=10, x2=90 + i * 10, y2=40),
                    confidence=0.92 - i * 0.05,
                    label="license_plate",
                    crop=PlateCropResponse(
                        media_type="image/png",
                        base64_data=valid_crop_base64(),
                        width=80,
                        height=30,
                    ),
                )
            )
        return ImageDetectionResponse(
            correlation_id=correlation_id,
            status="detected",
            detection_count=len(detections),
            image_width=200,
            image_height=150,
            inference_ms=12.5,
            total_ms=15.0,
            detections=detections,
        )


class MockOcr:
    def __init__(
        self,
        normalized_text: str = "YGN1234",
        confidence: float = 0.95,
        status: str = "recognized",
        review_reason: str | None = None,
    ) -> None:
        self.normalized_text = normalized_text
        self.confidence = confidence
        self.status = status
        self.review_reason = review_reason

    def recognize(self, crop_bytes: bytes, correlation_id: str) -> PlateOcrResponse:
        return PlateOcrResponse(
            correlation_id=correlation_id,
            status=self.status,
            review_reason=self.review_reason,
            raw_text=self.normalized_text,
            normalized_text=self.normalized_text,
            confidence=self.confidence,
            mode="recognition_only",
            inference_ms=8.0,
            total_ms=10.0,
            image_width=80,
            image_height=30,
        )


class FailingVehicleRepository:
    """Repository that raises a database error during lookup."""

    def get_by_normalized_plate(self, normalized_plate: str) -> None:
        raise RuntimeError("Database connection failure")


class FailingEvidenceStorage:
    """Storage adapter that fails object storage calls."""

    def store(
        self, bucket: str, object_path: str, content: bytes, content_type: str
    ) -> None:
        raise EvidenceStorageError(
            "STORAGE_UNAVAILABLE", "Storage destination unreachable"
        )

    def delete(self, bucket: str, object_path: str) -> None:
        raise EvidenceStorageError(
            "STORAGE_UNAVAILABLE", "Storage destination unreachable"
        )

    def exists(self, bucket: str, object_path: str) -> bool:
        return False

    def create_signed_access(
        self, bucket: str, object_path: str, lifetime_seconds: int
    ) -> None:
        raise EvidenceStorageError(
            "STORAGE_UNAVAILABLE", "Storage destination unreachable"
        )

    def resolve_signed_access(self, token: str) -> bytes:
        raise EvidenceStorageError(
            "STORAGE_UNAVAILABLE", "Storage destination unreachable"
        )


@pytest.fixture(autouse=True)
def reset_application_dependencies() -> None:
    deps = get_application_dependencies()
    deps.vehicles._records.clear()
    deps.detection_logs._records.clear()
    deps.recognition_activity._records.clear()
    deps.evidence_storage._objects.clear()
    deps.evidence_storage._grants.clear()


def test_e2e_full_workflow_authorized_and_operations() -> None:
    deps = get_application_dependencies()
    from app.core.config import get_settings

    settings = get_settings()

    # 1. Register an AUTHORIZED vehicle
    v_service = VehicleManagementService(deps.vehicles, clock=lambda: NOW)
    created = v_service.create(
        VehicleCreate(plate_number="YGN-1234", description="Owner vehicle")
    )
    assert created.normalized_plate == "YGN1234"
    assert created.status == "ACTIVE"

    # 2. Setup orchestration service
    detector = MockDetector(with_plate=True)
    ocr = MockOcr(normalized_text="YGN1234", confidence=0.95)
    decision_svc = AuthorizationDecisionService(
        deps.vehicles, settings, clock=lambda: NOW
    )
    logging_svc = DetectionLoggingService(
        deps.detection_logs,
        deps.evidence_storage,
        settings,
        clock=lambda: NOW,
    )
    orch_svc = RecognitionOrchestrationService(
        detector=detector,  # type: ignore[arg-type]
        ocr=ocr,  # type: ignore[arg-type]
        decision=decision_svc,
        logging=logging_svc,
        activity=deps.recognition_activity,
    )
    app.dependency_overrides[get_orchestration_service] = lambda: orch_svc

    try:
        # 3. Analyze image -> AUTHORIZED
        img = valid_jpeg_bytes()
        res = client.post(
            "/api/recognition/analyze", files={"file": ("car.jpg", img, "image/jpeg")}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "completed"
        assert data["message"] == "The vehicle record permits entry at this time."
        assert data["ocr"]["normalized_text"] == "YGN1234"
        assert data["logging"]["decision"]["decision"] == "AUTHORIZED"
        assert data["logging"]["decision"]["reason"] == "ACTIVE_MATCH"
        assert data["logging"]["log_persisted"] is True
        assert data["logging"]["evidence_available"] is True
        assert data["logging"]["failures"] == []
        assert "evidence_object_path" not in str(data)
        assert "evidence_bucket" not in str(data)
        assert len(deps.evidence_storage._objects) == 1
        correlation_id = data["correlation_id"]

        # 4. Verify history endpoint returns event with safe evidence metadata
        hist_res = client.get("/api/detections")
        assert hist_res.status_code == 200
        hist_data = hist_res.json()
        assert hist_data["total_items"] == 1
        assert hist_data["items"][0]["correlation_id"] == correlation_id
        assert hist_data["items"][0]["decision"] == "AUTHORIZED"
        assert hist_data["items"][0]["evidence_available"] is True
        assert "object_path" not in str(hist_data)

        # 5. Verify detection detail with safe evidence metadata
        detail_res = client.get(f"/api/detections/{correlation_id}")
        assert detail_res.status_code == 200
        detail_data = detail_res.json()
        assert detail_data["correlation_id"] == correlation_id
        assert detail_data["normalized_plate"] == "YGN1234"
        assert detail_data["decision"] == "AUTHORIZED"
        assert detail_data["evidence_available"] is True
        assert detail_data["evidence_access"] == "restricted"
        assert "object_path" not in str(detail_data)
        assert "signed_access" not in str(detail_data)

        # 6. Verify stats
        stats_res = client.get("/api/dashboard/statistics")
        assert stats_res.status_code == 200
        stats_data = stats_res.json()
        assert stats_data["total_recognitions"] == 1
        assert stats_data["authorized"] == 1
        assert stats_data["unauthorized"] == 0

        # 7. Verify alerts endpoint (no alerts for AUTHORIZED)
        alerts_res = client.get("/api/alerts")
        assert alerts_res.status_code == 200
        alerts_data = alerts_res.json()
        assert alerts_data["total_items"] == 0

    finally:
        app.dependency_overrides.clear()


def test_e2e_fail_closed_unauthorized_and_alerts() -> None:
    deps = get_application_dependencies()
    from app.core.config import get_settings

    settings = get_settings()

    # 1. Register a BLOCKED vehicle
    v_service = VehicleManagementService(deps.vehicles, clock=lambda: NOW)
    v_service.create(
        VehicleCreate(
            plate_number="BLK-9999", status="BLOCKED", description="Blocked intruder"
        )
    )

    # 2. Setup orchestration service
    detector = MockDetector(with_plate=True)
    ocr = MockOcr(normalized_text="BLK9999", confidence=0.92)
    decision_svc = AuthorizationDecisionService(
        deps.vehicles, settings, clock=lambda: NOW
    )
    logging_svc = DetectionLoggingService(
        deps.detection_logs,
        deps.evidence_storage,
        settings,
        clock=lambda: NOW,
    )
    orch_svc = RecognitionOrchestrationService(
        detector=detector,  # type: ignore[arg-type]
        ocr=ocr,  # type: ignore[arg-type]
        decision=decision_svc,
        logging=logging_svc,
        activity=deps.recognition_activity,
    )
    app.dependency_overrides[get_orchestration_service] = lambda: orch_svc

    try:
        # Analyze image -> UNAUTHORIZED / VEHICLE_BLOCKED
        img = valid_jpeg_bytes()
        res = client.post(
            "/api/recognition/analyze", files={"file": ("car.jpg", img, "image/jpeg")}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["logging"]["decision"]["decision"] == "UNAUTHORIZED"
        assert data["logging"]["decision"]["reason"] == "VEHICLE_BLOCKED"

        # Verify Alerts endpoint captures this security alert
        alerts_res = client.get("/api/alerts")
        assert alerts_res.status_code == 200
        alerts_data = alerts_res.json()
        assert alerts_data["total_items"] == 1
        assert alerts_data["items"][0]["reason"] == "VEHICLE_BLOCKED"

    finally:
        app.dependency_overrides.clear()


def test_e2e_fail_closed_inactive_expired_not_yet_valid_and_unknown() -> None:
    deps = get_application_dependencies()
    from app.core.config import get_settings

    settings = get_settings()
    v_service = VehicleManagementService(deps.vehicles, clock=lambda: NOW)

    # Create INACTIVE
    v_service.create(VehicleCreate(plate_number="INA-0001", status="INACTIVE"))
    # Create EXPIRED
    v_service.create(
        VehicleCreate(
            plate_number="EXP-0002",
            valid_from=NOW - timedelta(days=10),
            valid_until=NOW - timedelta(days=1),
        )
    )
    # Create NOT_YET_VALID
    v_service.create(
        VehicleCreate(
            plate_number="FUTURE-03",
            valid_from=NOW + timedelta(days=1),
            valid_until=NOW + timedelta(days=10),
        )
    )

    decision_svc = AuthorizationDecisionService(
        deps.vehicles, settings, clock=lambda: NOW
    )
    logging_svc = DetectionLoggingService(
        deps.detection_logs,
        deps.evidence_storage,
        settings,
        clock=lambda: NOW,
    )

    test_cases = [
        ("INA0001", "UNAUTHORIZED", "VEHICLE_INACTIVE"),
        ("EXP0002", "UNAUTHORIZED", "VEHICLE_EXPIRED"),
        ("FUTURE03", "UNAUTHORIZED", "VEHICLE_NOT_YET_VALID"),
        ("UNKNOWN99", "UNAUTHORIZED", "VEHICLE_NOT_FOUND"),
    ]

    for plate_text, expected_dec, expected_reason in test_cases:
        orch_svc = RecognitionOrchestrationService(
            detector=MockDetector(with_plate=True),  # type: ignore[arg-type]
            ocr=MockOcr(normalized_text=plate_text, confidence=0.95),  # type: ignore[arg-type]
            decision=decision_svc,
            logging=logging_svc,
            activity=deps.recognition_activity,
        )
        app.dependency_overrides[get_orchestration_service] = lambda: orch_svc
        try:
            res = client.post(
                "/api/recognition/analyze",
                files={"file": ("car.jpg", valid_jpeg_bytes(), "image/jpeg")},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["logging"]["decision"]["decision"] == expected_dec
            assert data["logging"]["decision"]["reason"] == expected_reason
        finally:
            app.dependency_overrides.clear()


def test_e2e_no_plate_detected_handling() -> None:
    deps = get_application_dependencies()
    from app.core.config import get_settings

    settings = get_settings()

    orch_svc = RecognitionOrchestrationService(
        detector=MockDetector(with_plate=False),  # type: ignore[arg-type]
        ocr=MockOcr(),  # type: ignore[arg-type]
        decision=AuthorizationDecisionService(
            deps.vehicles, settings, clock=lambda: NOW
        ),
        logging=DetectionLoggingService(
            deps.detection_logs,
            deps.evidence_storage,
            settings,
            clock=lambda: NOW,
        ),
        activity=deps.recognition_activity,
    )
    app.dependency_overrides[get_orchestration_service] = lambda: orch_svc

    try:
        res = client.post(
            "/api/recognition/analyze",
            files={"file": ("no_plate.jpg", valid_jpeg_bytes(), "image/jpeg")},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "no_plate_detected"
        assert data["detection_count"] == 0
        assert data["selected_plate"] is None

        # Verify stats record no-plate count
        stats_res = client.get("/api/dashboard/statistics")
        assert stats_res.status_code == 200
        assert stats_res.json()["no_plate"] == 1
    finally:
        app.dependency_overrides.clear()


def test_e2e_multiple_plates_selection() -> None:
    """Verify that when multiple plates are detected, primary candidate (index 0) is selected."""
    deps = get_application_dependencies()
    from app.core.config import get_settings

    settings = get_settings()
    v_service = VehicleManagementService(deps.vehicles, clock=lambda: NOW)
    v_service.create(VehicleCreate(plate_number="MULTI-1"))

    orch_svc = RecognitionOrchestrationService(
        detector=MockDetector(with_plate=True, detection_count=2),  # type: ignore[arg-type]
        ocr=MockOcr(normalized_text="MULTI1", confidence=0.91),  # type: ignore[arg-type]
        decision=AuthorizationDecisionService(
            deps.vehicles, settings, clock=lambda: NOW
        ),
        logging=DetectionLoggingService(
            deps.detection_logs,
            deps.evidence_storage,
            settings,
            clock=lambda: NOW,
        ),
        activity=deps.recognition_activity,
    )
    app.dependency_overrides[get_orchestration_service] = lambda: orch_svc

    try:
        res = client.post(
            "/api/recognition/analyze",
            files={"file": ("multi.jpg", valid_jpeg_bytes(), "image/jpeg")},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "completed"
        assert data["detection_count"] == 2
        assert data["selected_plate"]["bbox"]["x1"] == 10
    finally:
        app.dependency_overrides.clear()


def test_e2e_low_confidence_fails_to_manual_review() -> None:
    """Verify that OCR confidence below decision threshold fails to MANUAL_REVIEW."""
    deps = get_application_dependencies()
    from app.core.config import get_settings

    settings = get_settings()

    orch_svc = RecognitionOrchestrationService(
        detector=MockDetector(with_plate=True),  # type: ignore[arg-type]
        ocr=MockOcr(
            normalized_text="LOWCONF",
            confidence=0.50,
            status="manual_review",
            review_reason="OCR_LOW_CONFIDENCE",
        ),  # type: ignore[arg-type]
        decision=AuthorizationDecisionService(
            deps.vehicles, settings, clock=lambda: NOW
        ),
        logging=DetectionLoggingService(
            deps.detection_logs,
            deps.evidence_storage,
            settings,
            clock=lambda: NOW,
        ),
        activity=deps.recognition_activity,
    )
    app.dependency_overrides[get_orchestration_service] = lambda: orch_svc

    try:
        res = client.post(
            "/api/recognition/analyze",
            files={"file": ("lowconf.jpg", valid_jpeg_bytes(), "image/jpeg")},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["logging"]["decision"]["decision"] == "MANUAL_REVIEW"
        assert data["logging"]["decision"]["reason"] == "OCR_LOW_CONFIDENCE"
    finally:
        app.dependency_overrides.clear()


def test_e2e_database_lookup_failure_fails_to_manual_review() -> None:
    """Verify database/repository failure causes decision to fail closed to MANUAL_REVIEW without leaking exceptions."""
    deps = get_application_dependencies()
    from app.core.config import get_settings

    settings = get_settings()
    failing_repo = FailingVehicleRepository()

    orch_svc = RecognitionOrchestrationService(
        detector=MockDetector(with_plate=True),  # type: ignore[arg-type]
        ocr=MockOcr(normalized_text="FAILDB", confidence=0.95),  # type: ignore[arg-type]
        decision=AuthorizationDecisionService(
            failing_repo,
            settings,
            clock=lambda: NOW,  # type: ignore[arg-type]
        ),
        logging=DetectionLoggingService(
            deps.detection_logs,
            deps.evidence_storage,
            settings,
            clock=lambda: NOW,
        ),
        activity=deps.recognition_activity,
    )
    app.dependency_overrides[get_orchestration_service] = lambda: orch_svc

    try:
        res = client.post(
            "/api/recognition/analyze",
            files={"file": ("car.jpg", valid_jpeg_bytes(), "image/jpeg")},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["logging"]["decision"]["decision"] == "MANUAL_REVIEW"
        assert data["logging"]["decision"]["reason"] == "VEHICLE_LOOKUP_FAILED"
        assert "Database connection failure" not in res.text
    finally:
        app.dependency_overrides.clear()


def test_e2e_evidence_storage_failure_partial_failure() -> None:
    """Verify evidence storage failure yields partial_failure logging while preserving decision and suppressing raw tracebacks."""
    deps = get_application_dependencies()
    from app.core.config import get_settings

    settings = get_settings()
    v_service = VehicleManagementService(deps.vehicles, clock=lambda: NOW)
    v_service.create(VehicleCreate(plate_number="STORE-ERR"))

    failing_storage = FailingEvidenceStorage()

    orch_svc = RecognitionOrchestrationService(
        detector=MockDetector(with_plate=True),  # type: ignore[arg-type]
        ocr=MockOcr(normalized_text="STOREERR", confidence=0.95),  # type: ignore[arg-type]
        decision=AuthorizationDecisionService(
            deps.vehicles, settings, clock=lambda: NOW
        ),
        logging=DetectionLoggingService(
            deps.detection_logs,
            failing_storage,  # type: ignore[arg-type]
            settings,
            clock=lambda: NOW,
        ),
        activity=deps.recognition_activity,
    )
    app.dependency_overrides[get_orchestration_service] = lambda: orch_svc

    try:
        res = client.post(
            "/api/recognition/analyze",
            files={"file": ("car.jpg", valid_jpeg_bytes(), "image/jpeg")},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["logging"]["decision"]["decision"] == "AUTHORIZED"
        assert data["logging"]["status"] == "partial_failure"
        assert "EVIDENCE_STORAGE_FAILED" in data["logging"]["failures"]
        assert "Storage destination unreachable" not in res.text
    finally:
        app.dependency_overrides.clear()


def test_security_input_validation_and_sanitized_errors() -> None:
    # 1. Empty upload (returns 400 HTTP status code with IMAGE_EMPTY)
    empty_res = client.post(
        "/api/recognition/analyze", files={"file": ("empty.jpg", b"", "image/jpeg")}
    )
    assert empty_res.status_code == 400
    assert "error" in empty_res.json()
    assert empty_res.json()["error"]["code"] == "IMAGE_EMPTY"

    # 2. Corrupt upload
    corrupt_res = client.post(
        "/api/recognition/analyze",
        files={"file": ("corrupt.jpg", b"NOT_AN_IMAGE", "image/jpeg")},
    )
    assert corrupt_res.status_code == 400
    assert "error" in corrupt_res.json()
    assert corrupt_res.json()["error"]["code"] == "IMAGE_CONTENT_INVALID"

    # 3. Invalid vehicle creation input
    bad_v_res = client.post(
        "/api/authorized-vehicles",
        json={"plate_number": "!@#$%^"},
    )
    assert bad_v_res.status_code == 422
    assert "error" in bad_v_res.json()
    assert bad_v_res.json()["error"]["message"] == "The plate number is invalid."

    # Verify no raw exception or stack trace in response
    assert "Traceback" not in bad_v_res.text
    assert "Exception" not in bad_v_res.text
