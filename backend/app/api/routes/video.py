"""Day 17 API router for bounded short video processing."""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, UploadFile, status
from fastapi.responses import JSONResponse

from app.api.routes.recognition import get_orchestration_service
from app.core.config import get_settings
from app.schemas.video import VideoProcessingResponse
from app.services.recognition_orchestration import RecognitionOrchestrationService
from app.services.video_processing import (
    VideoProcessingService,
    VideoValidationError,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["video"])


@router.post(
    "/analyze-video",
    response_model=VideoProcessingResponse,
    status_code=status.HTTP_200_OK,
)
async def analyze_video(
    file: UploadFile,
    x_correlation_id: str | None = Header(default=None),
    orch_svc: RecognitionOrchestrationService = Depends(get_orchestration_service),
) -> VideoProcessingResponse | JSONResponse:
    """Analyze a bounded short video file frame by frame for license plates."""
    correlation_id = x_correlation_id or str(uuid4())
    filename = file.filename or ""
    if not filename:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "VIDEO_FILENAME_REQUIRED",
                    "message": "A video filename is required.",
                    "correlation_id": correlation_id,
                }
            },
        )

    try:
        max_bytes = get_settings().video_max_upload_bytes
        content = await file.read(max_bytes + 1)
    except Exception as exc:
        logger.warning(
            "Video file read failed for correlation_id=%s filename=%s error=%s",
            correlation_id,
            filename,
            exc,
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": "VIDEO_READ_FAILED",
                    "message": "Failed to read the uploaded video file.",
                    "correlation_id": correlation_id,
                }
            },
        )

    try:
        svc = VideoProcessingService(
            orchestration=orch_svc,
            settings=get_settings(),
        )
        return svc.process_video(
            video_bytes=content, filename=filename, correlation_id=correlation_id
        )
    except VideoValidationError as err:
        logger.info(
            "Video processing failed code=%s correlation_id=%s",
            err.code,
            correlation_id,
        )
        return JSONResponse(
            status_code=err.status_code,
            content={
                "error": {
                    "code": err.code,
                    "message": err.message,
                    "correlation_id": correlation_id,
                }
            },
        )
    except Exception:
        logger.error(
            "Unhandled video processing error correlation_id=%s",
            correlation_id,
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_VIDEO_ERROR",
                    "message": "An unexpected error occurred during video processing.",
                    "correlation_id": correlation_id,
                }
            },
        )
    finally:
        await file.close()
