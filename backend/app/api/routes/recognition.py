"""Image-input validation route for the recognition boundary."""

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse
from uuid import uuid4

from app.core.config import get_settings
from app.services.image_validation import ImageValidationError, validate_image_upload

router = APIRouter(prefix="/recognition", tags=["recognition"])


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
