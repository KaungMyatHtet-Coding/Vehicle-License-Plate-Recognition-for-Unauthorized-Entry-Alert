"""Focused Day 6 tests for deterministic, non-destructive plate preprocessing."""

from __future__ import annotations

import numpy as np
import pytest

from app.services import plate_preprocessing
from app.services.plate_preprocessing import (
    PlatePreprocessingError,
    PlatePreprocessingService,
    PreprocessingOptions,
    PreprocessingStage,
)


def sample_crop() -> np.ndarray:
    """Return a deterministic BGR crop with texture and contrast."""

    y, x = np.indices((40, 120))
    crop = np.empty((40, 120, 3), dtype=np.uint8)
    crop[:, :, 0] = (x * 2 + y) % 256
    crop[:, :, 1] = (x + y * 3) % 256
    crop[:, :, 2] = (x * 3 + y * 2) % 256
    return crop


def test_empty_stage_selection_preserves_original_without_variants() -> None:
    crop = sample_crop()
    before = crop.copy()

    result = PlatePreprocessingService().preprocess(crop, PreprocessingOptions())

    assert result.variants == ()
    assert np.array_equal(crop, before)
    assert np.array_equal(result.original, before)
    assert result.original is not crop
    assert result.original_metadata.name == "original"
    assert result.original_metadata.width == 120
    assert result.original_metadata.height == 40
    assert result.original_metadata.channels == 3
    assert result.original_metadata.dtype == "uint8"
    assert result.total_ms >= 0.0


def test_core_variants_have_deterministic_shapes_types_and_metadata() -> None:
    crop = sample_crop()
    before = crop.copy()
    options = PreprocessingOptions(
        stages=(
            PreprocessingStage.GRAYSCALE,
            PreprocessingStage.RESIZE,
            PreprocessingStage.DENOISE,
            PreprocessingStage.CONTRAST,
            PreprocessingStage.THRESHOLD,
        ),
        resize_width=240,
    )

    result = PlatePreprocessingService().preprocess(crop, options)

    assert np.array_equal(crop, before)
    variants = {variant.metadata.name: variant for variant in result.variants}
    assert tuple(variants) == (
        "grayscale",
        "resize",
        "denoise",
        "contrast",
        "threshold",
    )
    assert variants["grayscale"].image.shape == (40, 120)
    assert variants["resize"].image.shape == (80, 240, 3)
    assert variants["denoise"].image.shape == crop.shape
    assert variants["contrast"].image.shape == (40, 120)
    assert variants["threshold"].image.shape == (40, 120)
    assert all(variant.image.dtype == np.uint8 for variant in result.variants)
    assert set(np.unique(variants["threshold"].image)).issubset({0, 255})
    assert all(variant.metadata.elapsed_ms >= 0.0 for variant in result.variants)
    assert variants["resize"].metadata.parameters["target_width"] == 240
    assert variants["contrast"].metadata.parameters["method"] == "CLAHE"
    assert variants["threshold"].metadata.parameters["method"] == "OTSU_BINARY"


def test_each_variant_is_derived_from_original_not_previous_stage() -> None:
    crop = sample_crop()
    service = PlatePreprocessingService()

    combined = service.preprocess(
        crop,
        PreprocessingOptions(
            stages=(
                PreprocessingStage.THRESHOLD,
                PreprocessingStage.DENOISE,
                PreprocessingStage.GRAYSCALE,
            )
        ),
    )
    individual = {
        stage.value: service.preprocess(crop, PreprocessingOptions(stages=(stage,)))
        .variants[0]
        .image
        for stage in (
            PreprocessingStage.THRESHOLD,
            PreprocessingStage.DENOISE,
            PreprocessingStage.GRAYSCALE,
        )
    }

    for variant in combined.variants:
        assert np.array_equal(variant.image, individual[variant.metadata.name])


def test_grayscale_input_is_supported_and_copied() -> None:
    crop = sample_crop()[:, :, 0]

    result = PlatePreprocessingService().preprocess(
        crop, PreprocessingOptions(stages=(PreprocessingStage.GRAYSCALE,))
    )

    assert np.array_equal(result.variants[0].image, crop)
    assert result.variants[0].image is not crop
    assert result.variants[0].metadata.channels == 1


def test_resize_down_uses_bounded_aspect_preserving_shape() -> None:
    result = PlatePreprocessingService().preprocess(
        sample_crop(),
        PreprocessingOptions(stages=(PreprocessingStage.RESIZE,), resize_width=60),
    )

    variant = result.variants[0]
    assert variant.image.shape == (20, 60, 3)
    assert variant.metadata.parameters["interpolation"] == "area"


def test_deskew_is_explicit_optional_and_preserves_shape() -> None:
    options = PreprocessingOptions(
        stages=(PreprocessingStage.DESKEW,), deskew_angle_degrees=7.5
    )

    result = PlatePreprocessingService().preprocess(sample_crop(), options)

    assert result.variants[0].image.shape == (40, 120, 3)
    assert result.variants[0].metadata.parameters["angle_degrees"] == 7.5


def test_perspective_is_explicit_optional_with_requested_shape() -> None:
    options = PreprocessingOptions(
        stages=(PreprocessingStage.PERSPECTIVE,),
        perspective_points=(
            (5.0, 3.0),
            (114.0, 1.0),
            (118.0, 37.0),
            (2.0, 39.0),
        ),
        perspective_output_size=(200, 64),
    )

    result = PlatePreprocessingService().preprocess(sample_crop(), options)

    assert result.variants[0].image.shape == (64, 200, 3)
    assert result.variants[0].metadata.parameters["target_width"] == 200
    assert result.variants[0].metadata.parameters["target_height"] == 64


@pytest.mark.parametrize(
    ("crop", "code"),
    [
        (np.array([], dtype=np.uint8), "PREPROCESSING_CROP_INVALID"),
        (np.zeros((10, 10), dtype=np.float32), "PREPROCESSING_CROP_INVALID"),
        (np.zeros((10, 10, 4), dtype=np.uint8), "PREPROCESSING_CROP_INVALID"),
    ],
)
def test_invalid_crops_are_rejected_safely(crop: np.ndarray, code: str) -> None:
    with pytest.raises(PlatePreprocessingError) as caught:
        PlatePreprocessingService().preprocess(crop, PreprocessingOptions())

    assert caught.value.code == code


def test_duplicate_stages_are_rejected() -> None:
    with pytest.raises(PlatePreprocessingError) as caught:
        PreprocessingOptions(
            stages=(PreprocessingStage.GRAYSCALE, PreprocessingStage.GRAYSCALE)
        )

    assert caught.value.code == "PREPROCESSING_STAGE_DUPLICATE"


def test_unsupported_stage_value_is_rejected() -> None:
    with pytest.raises(PlatePreprocessingError) as caught:
        PreprocessingOptions(stages=("threshold",))  # type: ignore[arg-type]

    assert caught.value.code == "PREPROCESSING_STAGE_UNSUPPORTED"


@pytest.mark.parametrize("diameter", [0, 4, 33])
def test_denoise_diameter_is_bounded_and_odd(diameter: int) -> None:
    with pytest.raises(PlatePreprocessingError) as caught:
        PreprocessingOptions(denoise_diameter=diameter)

    assert caught.value.code == "PREPROCESSING_DENOISE_INVALID"


@pytest.mark.parametrize(
    ("clip_limit", "grid_size"),
    [(0.0, 8), (10.1, 8), (2.0, 0), (2.0, 33)],
)
def test_clahe_parameters_are_bounded(clip_limit: float, grid_size: int) -> None:
    with pytest.raises(PlatePreprocessingError) as caught:
        PreprocessingOptions(
            contrast_clip_limit=clip_limit,
            contrast_grid_size=grid_size,
        )

    assert caught.value.code == "PREPROCESSING_CONTRAST_INVALID"


def test_deskew_requires_explicit_bounded_angle() -> None:
    with pytest.raises(PlatePreprocessingError) as missing:
        PreprocessingOptions(stages=(PreprocessingStage.DESKEW,))
    with pytest.raises(PlatePreprocessingError) as invalid:
        PreprocessingOptions(deskew_angle_degrees=90.0)

    assert missing.value.code == "PREPROCESSING_DESKEW_REQUIRED"
    assert invalid.value.code == "PREPROCESSING_DESKEW_INVALID"


def test_perspective_requires_points_and_output_size() -> None:
    with pytest.raises(PlatePreprocessingError) as caught:
        PreprocessingOptions(stages=(PreprocessingStage.PERSPECTIVE,))

    assert caught.value.code == "PREPROCESSING_PERSPECTIVE_REQUIRED"


def test_perspective_points_must_form_ordered_convex_quadrilateral() -> None:
    with pytest.raises(PlatePreprocessingError) as caught:
        PreprocessingOptions(
            perspective_points=(
                (0.0, 0.0),
                (119.0, 39.0),
                (119.0, 0.0),
                (0.0, 39.0),
            )
        )

    assert caught.value.code == "PREPROCESSING_PERSPECTIVE_INVALID"


def test_perspective_output_area_is_bounded() -> None:
    with pytest.raises(PlatePreprocessingError) as caught:
        PreprocessingOptions(perspective_output_size=(4096, 4096))

    assert caught.value.code == "PREPROCESSING_DIMENSION_INVALID"


def test_perspective_points_must_be_inside_crop() -> None:
    options = PreprocessingOptions(
        stages=(PreprocessingStage.PERSPECTIVE,),
        perspective_points=(
            (-1.0, 0.0),
            (119.0, 0.0),
            (119.0, 39.0),
            (0.0, 39.0),
        ),
        perspective_output_size=(120, 40),
    )

    with pytest.raises(PlatePreprocessingError) as caught:
        PlatePreprocessingService().preprocess(sample_crop(), options)

    assert caught.value.code == "PREPROCESSING_PERSPECTIVE_INVALID"


def test_resize_rejects_output_that_exceeds_safe_height() -> None:
    narrow = np.zeros((100, 1, 3), dtype=np.uint8)
    options = PreprocessingOptions(
        stages=(PreprocessingStage.RESIZE,), resize_width=4096
    )

    with pytest.raises(PlatePreprocessingError) as caught:
        PlatePreprocessingService().preprocess(narrow, options)

    assert caught.value.code == "PREPROCESSING_DIMENSION_INVALID"


def test_resize_rejects_output_that_exceeds_safe_area(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(plate_preprocessing, "MAX_OUTPUT_PIXELS", 4_000)

    with pytest.raises(PlatePreprocessingError) as caught:
        PlatePreprocessingService().preprocess(
            sample_crop(),
            PreprocessingOptions(stages=(PreprocessingStage.RESIZE,), resize_width=120),
        )

    assert caught.value.code == "PREPROCESSING_DIMENSION_INVALID"


def test_error_contract_is_stable_and_does_not_expose_internal_details() -> None:
    with pytest.raises(PlatePreprocessingError) as caught:
        PreprocessingOptions(stages=(PreprocessingStage.DESKEW,))

    assert caught.value.code == "PREPROCESSING_DESKEW_REQUIRED"
    assert "D:\\" not in caught.value.message
    assert "Traceback" not in caught.value.message
