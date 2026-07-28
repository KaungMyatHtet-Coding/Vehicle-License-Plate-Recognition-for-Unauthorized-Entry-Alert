"""Configurable, non-destructive preprocessing for detected plate crops."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import StrEnum

import cv2
import numpy as np

MAX_OUTPUT_DIMENSION = 4096
MAX_OUTPUT_PIXELS = 16_000_000


class PreprocessingStage(StrEnum):
    """Supported independently selectable OCR-preparation operations."""

    GRAYSCALE = "grayscale"
    RESIZE = "resize"
    DENOISE = "denoise"
    CONTRAST = "contrast"
    THRESHOLD = "threshold"
    DESKEW = "deskew"
    PERSPECTIVE = "perspective"


class PlatePreprocessingError(ValueError):
    """Safe configuration or crop failure with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PreprocessingOptions:
    """Validated options; an empty stage tuple performs no transformations."""

    stages: tuple[PreprocessingStage, ...] = ()
    resize_width: int = 320
    denoise_diameter: int = 5
    contrast_clip_limit: float = 2.0
    contrast_grid_size: int = 8
    deskew_angle_degrees: float | None = None
    perspective_points: (
        tuple[
            tuple[float, float],
            tuple[float, float],
            tuple[float, float],
            tuple[float, float],
        ]
        | None
    ) = None
    perspective_output_size: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.stages, tuple):
            raise PlatePreprocessingError(
                "PREPROCESSING_STAGES_INVALID", "Preprocessing stages must be a tuple."
            )
        if any(not isinstance(stage, PreprocessingStage) for stage in self.stages):
            raise PlatePreprocessingError(
                "PREPROCESSING_STAGE_UNSUPPORTED",
                "A requested preprocessing stage is unsupported.",
            )
        if len(set(self.stages)) != len(self.stages):
            raise PlatePreprocessingError(
                "PREPROCESSING_STAGE_DUPLICATE",
                "Each preprocessing stage may be requested only once.",
            )
        _validate_dimension(self.resize_width, "resize width")
        if (
            type(self.denoise_diameter) is not int
            or self.denoise_diameter < 1
            or self.denoise_diameter > 31
            or self.denoise_diameter % 2 == 0
        ):
            raise PlatePreprocessingError(
                "PREPROCESSING_DENOISE_INVALID",
                "The denoise diameter must be an odd integer from 1 through 31.",
            )
        if (
            type(self.contrast_clip_limit) is not float
            or not math.isfinite(self.contrast_clip_limit)
            or not 0.1 <= self.contrast_clip_limit <= 10.0
        ):
            raise PlatePreprocessingError(
                "PREPROCESSING_CONTRAST_INVALID",
                "The contrast clip limit must be a finite float from 0.1 through 10.0.",
            )
        if (
            type(self.contrast_grid_size) is not int
            or not 1 <= self.contrast_grid_size <= 32
        ):
            raise PlatePreprocessingError(
                "PREPROCESSING_CONTRAST_INVALID",
                "The contrast grid size must be an integer from 1 through 32.",
            )
        if self.deskew_angle_degrees is not None:
            if (
                type(self.deskew_angle_degrees) is not float
                or not math.isfinite(self.deskew_angle_degrees)
                or not -45.0 <= self.deskew_angle_degrees <= 45.0
            ):
                raise PlatePreprocessingError(
                    "PREPROCESSING_DESKEW_INVALID",
                    "The deskew angle must be a finite float from -45.0 through 45.0.",
                )
        if PreprocessingStage.DESKEW in self.stages:
            if self.deskew_angle_degrees is None:
                raise PlatePreprocessingError(
                    "PREPROCESSING_DESKEW_REQUIRED",
                    "Deskew requires an explicit angle.",
                )
        if PreprocessingStage.PERSPECTIVE in self.stages:
            if self.perspective_points is None or self.perspective_output_size is None:
                raise PlatePreprocessingError(
                    "PREPROCESSING_PERSPECTIVE_REQUIRED",
                    "Perspective correction requires four points and an output size.",
                )
        if self.perspective_points is not None:
            _validate_perspective_points(self.perspective_points)
        if self.perspective_output_size is not None:
            _validate_output_size(self.perspective_output_size)


@dataclass(frozen=True)
class ImageStageMetadata:
    """Shape/type/timing evidence for an original or transformed image."""

    name: str
    width: int
    height: int
    channels: int
    dtype: str
    elapsed_ms: float
    parameters: dict[str, int | float | str] = field(default_factory=dict)


@dataclass(frozen=True)
class PreprocessedVariant:
    """One independently produced preprocessing variant."""

    metadata: ImageStageMetadata
    image: np.ndarray


@dataclass(frozen=True)
class PlatePreprocessingResult:
    """Original crop copy plus requested variants and total timing."""

    original: np.ndarray
    original_metadata: ImageStageMetadata
    variants: tuple[PreprocessedVariant, ...]
    total_ms: float


def _validate_dimension(value: int, label: str) -> None:
    if type(value) is not int or not 1 <= value <= MAX_OUTPUT_DIMENSION:
        raise PlatePreprocessingError(
            "PREPROCESSING_DIMENSION_INVALID",
            f"The {label} must be an integer from 1 through {MAX_OUTPUT_DIMENSION}.",
        )


def _validate_output_size(size: tuple[int, int]) -> None:
    if not isinstance(size, tuple) or len(size) != 2:
        raise PlatePreprocessingError(
            "PREPROCESSING_DIMENSION_INVALID",
            "The perspective output size must contain width and height.",
        )
    width, height = size
    _validate_dimension(width, "perspective output width")
    _validate_dimension(height, "perspective output height")
    if width * height > MAX_OUTPUT_PIXELS:
        raise PlatePreprocessingError(
            "PREPROCESSING_DIMENSION_INVALID",
            "The perspective output area exceeds the safe limit.",
        )


def _validate_perspective_points(
    points: tuple[
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
    ],
) -> None:
    if not isinstance(points, tuple) or len(points) != 4:
        raise PlatePreprocessingError(
            "PREPROCESSING_PERSPECTIVE_INVALID",
            "Perspective correction requires exactly four points.",
        )
    normalized: list[tuple[float, float]] = []
    for point in points:
        if not isinstance(point, tuple) or len(point) != 2:
            raise PlatePreprocessingError(
                "PREPROCESSING_PERSPECTIVE_INVALID",
                "Each perspective point must contain x and y.",
            )
        x, y = point
        if (
            type(x) is not float
            or type(y) is not float
            or not math.isfinite(x)
            or not math.isfinite(y)
        ):
            raise PlatePreprocessingError(
                "PREPROCESSING_PERSPECTIVE_INVALID",
                "Perspective coordinates must be finite floats.",
            )
        normalized.append((x, y))
    if len(set(normalized)) != 4:
        raise PlatePreprocessingError(
            "PREPROCESSING_PERSPECTIVE_INVALID",
            "Perspective points must be distinct.",
        )
    polygon = np.asarray(normalized, dtype=np.float32)
    if abs(cv2.contourArea(polygon)) < 1.0 or not cv2.isContourConvex(polygon):
        raise PlatePreprocessingError(
            "PREPROCESSING_PERSPECTIVE_INVALID",
            "Perspective points must form an ordered convex quadrilateral.",
        )


def _validate_crop(crop: np.ndarray) -> None:
    if not isinstance(crop, np.ndarray):
        raise PlatePreprocessingError(
            "PREPROCESSING_CROP_INVALID", "The plate crop must be a NumPy array."
        )
    if crop.dtype != np.uint8:
        raise PlatePreprocessingError(
            "PREPROCESSING_CROP_INVALID", "The plate crop must use uint8 pixels."
        )
    if crop.ndim not in (2, 3):
        raise PlatePreprocessingError(
            "PREPROCESSING_CROP_INVALID",
            "The plate crop must be grayscale or BGR color.",
        )
    if crop.ndim == 3 and crop.shape[2] != 3:
        raise PlatePreprocessingError(
            "PREPROCESSING_CROP_INVALID",
            "A color plate crop must have exactly three channels.",
        )
    if crop.size == 0 or crop.shape[0] < 1 or crop.shape[1] < 1:
        raise PlatePreprocessingError(
            "PREPROCESSING_CROP_INVALID", "The plate crop must not be empty."
        )


def _grayscale(crop: np.ndarray) -> np.ndarray:
    if crop.ndim == 2:
        return crop.copy()
    return cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)


def _metadata(
    name: str,
    image: np.ndarray,
    elapsed_ms: float,
    parameters: dict[str, int | float | str] | None = None,
) -> ImageStageMetadata:
    channels = 1 if image.ndim == 2 else int(image.shape[2])
    return ImageStageMetadata(
        name=name,
        width=int(image.shape[1]),
        height=int(image.shape[0]),
        channels=channels,
        dtype=str(image.dtype),
        elapsed_ms=elapsed_ms,
        parameters=parameters or {},
    )


class PlatePreprocessingService:
    """Produce only explicitly requested variants from an unchanged crop."""

    def preprocess(
        self, crop: np.ndarray, options: PreprocessingOptions
    ) -> PlatePreprocessingResult:
        """Return a preserved original and independent OCR-ready variants."""

        _validate_crop(crop)
        if not isinstance(options, PreprocessingOptions):
            raise PlatePreprocessingError(
                "PREPROCESSING_OPTIONS_INVALID",
                "Preprocessing options are invalid.",
            )

        total_started = time.perf_counter()
        original = crop.copy()
        original_metadata = _metadata("original", original, 0.0)
        variants: list[PreprocessedVariant] = []

        for stage in options.stages:
            started = time.perf_counter()
            image, parameters = self._apply(stage, original, options)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
            variants.append(
                PreprocessedVariant(
                    metadata=_metadata(stage.value, image, elapsed_ms, parameters),
                    image=image,
                )
            )

        total_ms = round((time.perf_counter() - total_started) * 1000, 3)
        return PlatePreprocessingResult(
            original=original,
            original_metadata=original_metadata,
            variants=tuple(variants),
            total_ms=total_ms,
        )

    @staticmethod
    def _apply(
        stage: PreprocessingStage,
        original: np.ndarray,
        options: PreprocessingOptions,
    ) -> tuple[np.ndarray, dict[str, int | float | str]]:
        if stage is PreprocessingStage.GRAYSCALE:
            return _grayscale(original), {"color": "BGR_TO_GRAY"}
        if stage is PreprocessingStage.RESIZE:
            height, width = original.shape[:2]
            resized_height = max(1, round(height * options.resize_width / width))
            if (
                resized_height > MAX_OUTPUT_DIMENSION
                or options.resize_width * resized_height > MAX_OUTPUT_PIXELS
            ):
                raise PlatePreprocessingError(
                    "PREPROCESSING_DIMENSION_INVALID",
                    "The aspect-preserving resize exceeds safe output limits.",
                )
            resized = cv2.resize(
                original,
                (options.resize_width, resized_height),
                interpolation=(
                    cv2.INTER_CUBIC if options.resize_width > width else cv2.INTER_AREA
                ),
            )
            return resized, {
                "target_width": options.resize_width,
                "interpolation": ("cubic" if options.resize_width > width else "area"),
            }
        if stage is PreprocessingStage.DENOISE:
            return cv2.bilateralFilter(original, options.denoise_diameter, 50, 50), {
                "diameter": options.denoise_diameter,
                "sigma_color": 50,
                "sigma_space": 50,
            }
        if stage is PreprocessingStage.CONTRAST:
            grayscale = _grayscale(original)
            clahe = cv2.createCLAHE(
                clipLimit=options.contrast_clip_limit,
                tileGridSize=(
                    options.contrast_grid_size,
                    options.contrast_grid_size,
                ),
            )
            return clahe.apply(grayscale), {
                "method": "CLAHE",
                "clip_limit": options.contrast_clip_limit,
                "grid_size": options.contrast_grid_size,
            }
        if stage is PreprocessingStage.THRESHOLD:
            grayscale = _grayscale(original)
            threshold_value, thresholded = cv2.threshold(
                grayscale, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
            return thresholded, {
                "method": "OTSU_BINARY",
                "threshold": round(float(threshold_value), 3),
            }
        if stage is PreprocessingStage.DESKEW:
            angle = options.deskew_angle_degrees
            if angle is None:  # guarded by options validation
                raise PlatePreprocessingError(
                    "PREPROCESSING_DESKEW_REQUIRED",
                    "Deskew requires an explicit angle.",
                )
            height, width = original.shape[:2]
            matrix = cv2.getRotationMatrix2D(
                ((width - 1) / 2.0, (height - 1) / 2.0), angle, 1.0
            )
            return cv2.warpAffine(
                original,
                matrix,
                (width, height),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REPLICATE,
            ), {
                "angle_degrees": angle,
                "border_mode": "replicate",
            }
        if stage is PreprocessingStage.PERSPECTIVE:
            points = options.perspective_points
            output_size = options.perspective_output_size
            if points is None or output_size is None:  # guarded by validation
                raise PlatePreprocessingError(
                    "PREPROCESSING_PERSPECTIVE_REQUIRED",
                    "Perspective correction requires points and an output size.",
                )
            height, width = original.shape[:2]
            if any(
                x < 0.0 or y < 0.0 or x > width - 1 or y > height - 1 for x, y in points
            ):
                raise PlatePreprocessingError(
                    "PREPROCESSING_PERSPECTIVE_INVALID",
                    "Perspective points must be inside the source crop.",
                )
            target_width, target_height = output_size
            source = np.asarray(points, dtype=np.float32)
            target = np.asarray(
                [
                    (0, 0),
                    (target_width - 1, 0),
                    (target_width - 1, target_height - 1),
                    (0, target_height - 1),
                ],
                dtype=np.float32,
            )
            matrix = cv2.getPerspectiveTransform(source, target)
            return cv2.warpPerspective(
                original,
                matrix,
                (target_width, target_height),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REPLICATE,
            ), {
                "target_width": target_width,
                "target_height": target_height,
                "border_mode": "replicate",
            }
        raise PlatePreprocessingError(
            "PREPROCESSING_STAGE_UNSUPPORTED",
            "A requested preprocessing stage is unsupported.",
        )
