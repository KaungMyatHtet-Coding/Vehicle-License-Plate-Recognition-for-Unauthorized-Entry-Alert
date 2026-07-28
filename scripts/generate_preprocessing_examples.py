"""Generate the documented Day 6 preprocessing contact sheet."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.plate_preprocessing import (  # noqa: E402
    PlatePreprocessingService,
    PreprocessingOptions,
    PreprocessingStage,
)

DEFAULT_INPUT = Path("sample-data/evaluation/synthetic_plate_white.png")
DEFAULT_OUTPUT = Path("docs/day6_preprocessing_examples.png")
PLATE_BOX = (220, 320, 420, 370)


def build_contact_sheet(input_path: Path) -> np.ndarray:
    """Create a deterministic visual comparison from a generated legal fixture."""

    image = cv2.imread(str(input_path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("The input example could not be decoded.")
    x1, y1, x2, y2 = PLATE_BOX
    crop = image[y1:y2, x1:x2].copy()
    if crop.size == 0:
        raise ValueError("The documented plate crop is empty.")

    result = PlatePreprocessingService().preprocess(
        crop,
        PreprocessingOptions(
            stages=(
                PreprocessingStage.GRAYSCALE,
                PreprocessingStage.RESIZE,
                PreprocessingStage.DENOISE,
                PreprocessingStage.CONTRAST,
                PreprocessingStage.THRESHOLD,
                PreprocessingStage.DESKEW,
                PreprocessingStage.PERSPECTIVE,
            ),
            resize_width=320,
            deskew_angle_degrees=5.0,
            perspective_points=(
                (3.0, 2.0),
                (196.0, 0.0),
                (199.0, 47.0),
                (0.0, 49.0),
            ),
            perspective_output_size=(200, 50),
        ),
    )
    images = [result.original, *(variant.image for variant in result.variants)]
    labels = ["original", *(variant.metadata.name for variant in result.variants)]

    tile_width = 240
    tile_height = 100
    tiles: list[np.ndarray] = []
    for label, variant in zip(labels, images, strict=True):
        if variant.ndim == 2:
            variant = cv2.cvtColor(variant, cv2.COLOR_GRAY2BGR)
        scale = min(tile_width / variant.shape[1], 70 / variant.shape[0])
        resized = cv2.resize(
            variant,
            (
                max(1, round(variant.shape[1] * scale)),
                max(1, round(variant.shape[0] * scale)),
            ),
            interpolation=cv2.INTER_NEAREST,
        )
        tile = np.full((tile_height, tile_width, 3), 245, dtype=np.uint8)
        x_offset = (tile_width - resized.shape[1]) // 2
        y_offset = 25 + (70 - resized.shape[0]) // 2
        tile[
            y_offset : y_offset + resized.shape[0],
            x_offset : x_offset + resized.shape[1],
        ] = resized
        cv2.putText(
            tile,
            label,
            (8, 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (20, 20, 20),
            1,
            cv2.LINE_AA,
        )
        tiles.append(tile)

    blank = np.full_like(tiles[0], 245)
    while len(tiles) % 4:
        tiles.append(blank.copy())
    rows = [cv2.hconcat(tiles[index : index + 4]) for index in range(0, len(tiles), 4)]
    return cv2.vconcat(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the Day 6 preprocessing visual example."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    try:
        sheet = build_contact_sheet(args.input)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(args.output), sheet):
            raise OSError("OpenCV could not encode the output image.")
    except (OSError, ValueError) as exc:
        print(f"example generation error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
