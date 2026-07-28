"""Image-input validation route for the recognition boundary."""

import threading
from uuid import uuid4

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.services.plate_detection import PlateDetectionError, PlateDetectionService
from app.services.image_validation import ImageValidationError, validate_image_upload

router = APIRouter(prefix="/recognition", tags=["recognition"])
_detection_service: PlateDetectionService | None = None
_detection_service_lock = threading.Lock()


def get_detection_service() -> PlateDetectionService:
    """Create the lightweight service once; its model remains lazy."""

    global _detection_service
    if _detection_service is None:
        with _detection_service_lock:
            if _detection_service is None:
                _detection_service = PlateDetectionService(get_settings())
    return _detection_service


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
