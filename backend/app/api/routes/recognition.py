"""Image-input validation route for the recognition boundary."""

import threading
from uuid import uuid4

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.repositories.memory import (
    InMemoryAuthorizedVehicleRepository,
    InMemoryDetectionLogRepository,
)
from app.services.authorization_decision import AuthorizationDecisionService
from app.services.detection_logging import DetectionLoggingService
from app.services.evidence_storage import InMemoryEvidenceStorage
from app.services.ocr_recognition import PlateOcrError, PlateOcrService
from app.services.plate_detection import PlateDetectionError, PlateDetectionService
from app.services.image_validation import ImageValidationError, validate_image_upload
from app.services.recognition_orchestration import (
    RecognitionOrchestrationError,
    RecognitionOrchestrationService,
)

router = APIRouter(prefix="/recognition", tags=["recognition"])
_detection_service: PlateDetectionService | None = None
_detection_service_lock = threading.Lock()
_ocr_service: PlateOcrService | None = None
_ocr_service_lock = threading.Lock()
_orchestration_service: RecognitionOrchestrationService | None = None
_orchestration_service_lock = threading.Lock()


def get_detection_service() -> PlateDetectionService:
    """Create the lightweight service once; its model remains lazy."""

    global _detection_service
    if _detection_service is None:
        with _detection_service_lock:
            if _detection_service is None:
                _detection_service = PlateDetectionService(get_settings())
    return _detection_service


def get_ocr_service() -> PlateOcrService:
    """Create the lightweight OCR service once; its engine remains lazy."""

    global _ocr_service
    if _ocr_service is None:
        with _ocr_service_lock:
            if _ocr_service is None:
                _ocr_service = PlateOcrService(get_settings())
    return _ocr_service


def get_orchestration_service() -> RecognitionOrchestrationService:
    """Compose process-local adapters once while external adapters remain deferred."""

    global _orchestration_service
    if _orchestration_service is None:
        with _orchestration_service_lock:
            if _orchestration_service is None:
                settings = get_settings()
                vehicles = InMemoryAuthorizedVehicleRepository()
                logs = InMemoryDetectionLogRepository()
                storage = InMemoryEvidenceStorage()
                _orchestration_service = RecognitionOrchestrationService(
                    get_detection_service(),
                    get_ocr_service(),
                    AuthorizationDecisionService(vehicles, settings),
                    DetectionLoggingService(logs, storage, settings),
                )
    return _orchestration_service


def _error_response(
    error: ImageValidationError
    | PlateDetectionError
    | PlateOcrError
    | RecognitionOrchestrationError,
    correlation_id: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={
            "error": {
                "code": error.code,
                "message": error.message,
                "correlation_id": correlation_id,
            }
        },
    )


@router.post("/validate-image", summary="Validate an image input")
async def validate_image(file: UploadFile | None = File(default=None)) -> JSONResponse:
    """Validate image bytes without storing or recognizing a license plate."""

    try:
        result = await validate_image_upload(file, get_settings())
    except ImageValidationError as error:
        correlation_id = str(uuid4())
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "correlation_id": correlation_id,
                }
            },
        )
    return JSONResponse(status_code=200, content=result.model_dump())


@router.post("/detect-plates", summary="Detect and crop license plates")
async def detect_plates(file: UploadFile | None = File(default=None)) -> JSONResponse:
    """Validate one transient image and detect zero, one, or multiple plates."""

    try:
        validation = await validate_image_upload(file, get_settings())
        if file is None:  # pragma: no cover - validation always raises first
            raise AssertionError("validated upload is unexpectedly missing")
        image_bytes = await file.read()
        await file.seek(0)
        result = get_detection_service().detect(image_bytes, validation.correlation_id)
    except ImageValidationError as error:
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "correlation_id": str(uuid4()),
                }
            },
        )
    except PlateDetectionError as error:
        correlation_id = (
            validation.correlation_id if "validation" in locals() else str(uuid4())
        )
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "correlation_id": correlation_id,
                }
            },
        )
    return JSONResponse(status_code=200, content=result.model_dump())


@router.post("/recognize-plate", summary="Recognize one validated plate crop")
async def recognize_plate(file: UploadFile | None = File(default=None)) -> JSONResponse:
    """Validate a transient plate crop and return OCR text without a decision."""

    try:
        validation = await validate_image_upload(file, get_settings())
        if file is None:  # pragma: no cover - validation always raises first
            raise AssertionError("validated upload is unexpectedly missing")
        image_bytes = await file.read()
        await file.seek(0)
        result = get_ocr_service().recognize(image_bytes, validation.correlation_id)
    except ImageValidationError as error:
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "correlation_id": str(uuid4()),
                }
            },
        )
    except PlateOcrError as error:
        correlation_id = (
            validation.correlation_id if "validation" in locals() else str(uuid4())
        )
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "correlation_id": correlation_id,
                }
            },
        )
    return JSONResponse(status_code=200, content=result.model_dump())


@router.post("/analyze", summary="Analyze one vehicle image")
async def analyze_image(
    file: UploadFile | None = File(default=None),
    service: RecognitionOrchestrationService = Depends(get_orchestration_service),
) -> JSONResponse:
    """Validate and run one transient vehicle image through the full pipeline."""

    correlation_id = str(uuid4())
    try:
        validation = await validate_image_upload(file, get_settings())
        correlation_id = validation.correlation_id
        if file is None:  # pragma: no cover - validation always raises first
            raise AssertionError("validated upload is unexpectedly missing")
        image_bytes = await file.read()
        await file.seek(0)
        result = service.recognize(image_bytes, correlation_id)
    except (
        ImageValidationError,
        PlateDetectionError,
        PlateOcrError,
        RecognitionOrchestrationError,
    ) as error:
        return _error_response(error, correlation_id)
    except Exception:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "RECOGNITION_FAILED",
                    "message": "Recognition could not be completed.",
                    "correlation_id": correlation_id,
                }
            },
        )
    finally:
        if file is not None:
            await file.close()
    return JSONResponse(status_code=200, content=result.model_dump(mode="json"))
