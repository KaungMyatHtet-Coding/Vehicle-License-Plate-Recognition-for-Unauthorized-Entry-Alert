"""Safe, transient validation for supported image uploads."""

from __future__ import annotations

import warnings
from io import BytesIO
from pathlib import PurePath
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image, ImageFile

from app.core.config import Settings
from app.schemas.image import ImageValidationResponse

ImageFile.LOAD_TRUNCATED_IMAGES = False

SUPPORTED_IMAGES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "JPEG": (("image/jpeg", "image/jpg"), (".jpg", ".jpeg")),
    "PNG": (("image/png",), (".png",)),
}


class ImageValidationError(Exception):
    """Expected client input failure with a stable code and HTTP status."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _correlation_id() -> str:
    return str(uuid4())


def _safe_extension(filename: str) -> str:
    """Return a lowercase extension only for a plain filename."""

    if not filename or "/" in filename or "\\" in filename:
        raise ImageValidationError(
            "IMAGE_FILENAME_INVALID", "The filename must be a plain filename.", 400
        )
    return PurePath(filename).suffix.lower()


def _raise(code: str, message: str, status_code: int) -> None:
    raise ImageValidationError(code, message, status_code)


def _dimensions_supported(width: int, height: int, settings: Settings) -> bool:
    return (
        settings.min_image_width <= width <= settings.max_image_width
        and settings.min_image_height <= height <= settings.max_image_height
        and width * height <= settings.max_image_pixels
    )


async def validate_image_upload(
    upload: UploadFile | None, settings: Settings
) -> ImageValidationResponse:
    """Validate an image in memory and reset the stream for later processing."""

    correlation_id = _correlation_id()
    if upload is None:
        _raise("IMAGE_FILE_REQUIRED", "An image file is required.", 400)

    filename = upload.filename or ""
    extension = _safe_extension(filename)
    content_type = (upload.content_type or "").lower()
    if extension not in {".jpg", ".jpeg", ".png"}:
        _raise(
            "IMAGE_EXTENSION_UNSUPPORTED",
            "Only JPEG and PNG images are supported.",
            415,
        )
    if content_type not in {"image/jpeg", "image/jpg", "image/png"}:
        _raise(
            "IMAGE_MIME_UNSUPPORTED", "Only JPEG and PNG MIME types are supported.", 415
        )

    try:
        data = await upload.read(settings.max_image_bytes + 1)
    finally:
        await upload.seek(0)

    if not data:
        _raise("IMAGE_EMPTY", "The image file is empty.", 400)
    if len(data) > settings.max_image_bytes:
        _raise("IMAGE_TOO_LARGE", "The image exceeds the configured byte limit.", 413)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as inspected:
                detected_format = inspected.format or ""
                width, height = inspected.size
                inspected.verify()
            if not _dimensions_supported(width, height, settings):
                _raise(
                    "IMAGE_DIMENSIONS_UNSUPPORTED",
                    "The image dimensions are outside the supported limits.",
                    422,
                )
            with Image.open(BytesIO(data)) as decoded:
                decoded.load()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        _raise(
            "IMAGE_DECOMPRESSION_UNSAFE", "The image exceeds safe decoding limits.", 422
        )
    except (OSError, ValueError):
        _raise("IMAGE_CONTENT_INVALID", "The file is not a valid supported image.", 400)

    format_rules = SUPPORTED_IMAGES.get(detected_format)
    if format_rules is None:
        _raise(
            "IMAGE_FORMAT_UNSUPPORTED",
            "The decoded image format is not supported.",
            415,
        )
    expected_mimes, expected_extensions = format_rules
    if content_type not in expected_mimes or extension not in expected_extensions:
        _raise(
            "IMAGE_CONTENT_MISMATCH",
            "The filename, MIME type, and decoded image format do not match.",
            415,
        )
    return ImageValidationResponse(
        correlation_id=correlation_id,
        filename=filename,
        content_type=content_type,
        detected_format=detected_format,
        size_bytes=len(data),
        width=width,
        height=height,
    )
