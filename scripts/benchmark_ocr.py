"""Reproducible Day 7 OCR benchmark over labeled synthetic plate crops."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

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

DEFAULT_INPUT = Path("sample-data/evaluation")
DEFAULT_OUTPUT = Path("docs/day7_ocr_benchmark.json")
VARIANT_STAGES = (
    PreprocessingStage.GRAYSCALE,
    PreprocessingStage.RESIZE,
    PreprocessingStage.DENOISE,
    PreprocessingStage.CONTRAST,
    PreprocessingStage.THRESHOLD,
)
CANDIDATES = ("rapidocr_recognition_only", "rapidocr_full")
ALLOWED_CHARACTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"


class BenchmarkError(RuntimeError):
    """Expected benchmark input or OCR dependency failure."""


class OcrEngine(Protocol):
    """Small adapter boundary used by the real engine and focused tests."""

    version: str

    def recognize(
        self, image: np.ndarray, candidate: str
    ) -> tuple[str, float | None]: ...


@dataclass(frozen=True)
class LabeledCrop:
    """One ground-truth plate crop with exclusive-edge coordinates."""

    fixture: str
    plate_index: int
    expected_text: str
    bbox: tuple[int, int, int, int]
    image: np.ndarray


@dataclass(frozen=True)
class SampleResult:
    """Raw measured OCR result for one crop, variant, and candidate."""

    fixture: str
    plate_index: int
    candidate: str
    variant: str
    expected_text: str
    raw_text: str
    normalized_text: str
    confidence: float | None
    exact_match: bool
    correct_characters: int
    expected_characters: int
    latency_ms: float


def normalize_plate_text(value: str) -> str:
    """Normalize spacing/case while retaining only the declared plate alphabet."""

    upper = value.upper()
    return "".join(character for character in upper if character in ALLOWED_CHARACTERS)


def edit_distance(left: str, right: str) -> int:
    """Return deterministic Levenshtein distance without external dependencies."""

    previous = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_character in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_character != right_character),
                )
            )
        previous = current
    return previous[-1]


def character_score(expected: str, actual: str) -> tuple[int, int]:
    """Return edit-distance-derived correct and expected character counts."""

    expected_count = len(expected)
    return max(0, expected_count - edit_distance(expected, actual)), expected_count


def load_labeled_crops(input_dir: Path) -> tuple[list[LabeledCrop], int]:
    """Validate the manifest and return copied ground-truth crops."""

    manifest_path = input_dir / "ground_truth.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(
            "The OCR ground-truth manifest is unavailable or invalid."
        ) from exc
    if not isinstance(payload, list) or not payload:
        raise BenchmarkError("The OCR ground-truth manifest must be a non-empty list.")

    crops: list[LabeledCrop] = []
    control_count = 0
    for entry in payload:
        if not isinstance(entry, dict):
            raise BenchmarkError("Each OCR fixture entry must be an object.")
        fixture = entry.get("file")
        boxes = entry.get("bounding_boxes")
        expected_detections = entry.get("expected_detections")
        if (
            not isinstance(fixture, str)
            or not isinstance(boxes, list)
            or type(expected_detections) is not int
            or expected_detections != len(boxes)
        ):
            raise BenchmarkError("An OCR fixture entry has an invalid contract.")
        image = cv2.imread(str(input_dir / fixture), cv2.IMREAD_COLOR)
        if image is None:
            raise BenchmarkError("An OCR fixture could not be decoded.")
        if not boxes:
            control_count += 1
        for plate_index, box in enumerate(boxes):
            if not isinstance(box, dict) or not isinstance(box.get("text"), str):
                raise BenchmarkError("Every labeled OCR box must contain text.")
            coordinates = tuple(box.get(key) for key in ("x1", "y1", "x2", "y2"))
            if len(coordinates) != 4 or any(
                type(value) is not int for value in coordinates
            ):
                raise BenchmarkError("OCR crop coordinates must be integers.")
            x1, y1, x2, y2 = coordinates
            height, width = image.shape[:2]
            if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                raise BenchmarkError("An OCR crop lies outside its fixture.")
            crop = image[y1:y2, x1:x2].copy()
            crops.append(
                LabeledCrop(
                    fixture=fixture,
                    plate_index=plate_index,
                    expected_text=box["text"],
                    bbox=(x1, y1, x2, y2),
                    image=crop,
                )
            )
    if not crops:
        raise BenchmarkError("The OCR benchmark requires at least one labeled crop.")
    return crops, control_count


def build_variants(crop: np.ndarray) -> dict[str, np.ndarray]:
    """Use the Day 6 contract to create independent variants from the original."""

    result = PlatePreprocessingService().preprocess(
        crop,
        PreprocessingOptions(stages=VARIANT_STAGES, resize_width=320),
    )
    return {
        "original": result.original,
        **{variant.metadata.name: variant.image for variant in result.variants},
    }


class RapidOcrEngine:
    """One local ONNX Runtime CPU engine reused for the complete benchmark."""

    version: str

    def __init__(self) -> None:
        try:
            from rapidocr import RapidOCR

            self.version = importlib.metadata.version("rapidocr")
            self._engine = RapidOCR()
            providers = {
                tuple(component.session.session.get_providers())
                for component in (
                    self._engine.text_det,
                    self._engine.text_cls,
                    self._engine.text_rec,
                )
            }
            if providers != {("CPUExecutionProvider",)}:
                raise BenchmarkError(
                    "RapidOCR must use ONNX Runtime CPU execution only."
                )
        except (ImportError, importlib.metadata.PackageNotFoundError) as exc:
            raise BenchmarkError(
                "RapidOCR is unavailable; install the pinned Day 7 development dependency."
            ) from exc
        except Exception as exc:
            raise BenchmarkError(
                "RapidOCR could not initialize for the benchmark."
            ) from exc

    def recognize(self, image: np.ndarray, candidate: str) -> tuple[str, float | None]:
        try:
            if candidate == "rapidocr_recognition_only":
                output = self._engine(image, use_det=False, use_cls=False, use_rec=True)
            elif candidate == "rapidocr_full":
                output = self._engine(image, use_det=True, use_cls=True, use_rec=True)
            else:
                raise BenchmarkError("An unsupported OCR candidate was requested.")
        except BenchmarkError:
            raise
        except Exception as exc:
            raise BenchmarkError("OCR inference failed during the benchmark.") from exc

        texts = tuple(getattr(output, "txts", ()) or ())
        scores = tuple(getattr(output, "scores", ()) or ())
        text = " ".join(str(value) for value in texts).strip()
        confidence = round(float(sum(scores) / len(scores)), 6) if scores else None
        return text, confidence


def run_benchmark(input_dir: Path, engine: OcrEngine) -> tuple[list[SampleResult], int]:
    """Measure both OCR modes over every crop and Day 6 variant."""

    crops, control_count = load_labeled_crops(input_dir)
    results: list[SampleResult] = []
    for crop in crops:
        expected = normalize_plate_text(crop.expected_text)
        for variant_name, image in build_variants(crop.image).items():
            for candidate in CANDIDATES:
                started = time.perf_counter()
                raw_text, confidence = engine.recognize(image, candidate)
                latency_ms = round((time.perf_counter() - started) * 1000, 3)
                normalized = normalize_plate_text(raw_text)
                correct, expected_count = character_score(expected, normalized)
                results.append(
                    SampleResult(
                        fixture=crop.fixture,
                        plate_index=crop.plate_index,
                        candidate=candidate,
                        variant=variant_name,
                        expected_text=crop.expected_text,
                        raw_text=raw_text,
                        normalized_text=normalized,
                        confidence=confidence,
                        exact_match=normalized == expected,
                        correct_characters=correct,
                        expected_characters=expected_count,
                        latency_ms=latency_ms,
                    )
                )
    return results, control_count


def summarize(results: list[SampleResult]) -> dict[str, dict[str, float | int]]:
    """Aggregate only values computed from retained raw sample results."""

    summary: dict[str, dict[str, float | int]] = {}
    for candidate in CANDIDATES:
        selected = [result for result in results if result.candidate == candidate]
        correct = sum(result.correct_characters for result in selected)
        expected = sum(result.expected_characters for result in selected)
        summary[candidate] = {
            "samples": len(selected),
            "exact_matches": sum(result.exact_match for result in selected),
            "exact_match_rate": round(
                sum(result.exact_match for result in selected) / len(selected), 6
            ),
            "correct_characters": correct,
            "expected_characters": expected,
            "character_accuracy": round(correct / expected, 6),
            "mean_latency_ms": round(
                sum(result.latency_ms for result in selected) / len(selected), 3
            ),
        }
    return summary


def write_results(
    output_path: Path,
    input_dir: Path,
    engine: OcrEngine,
    results: list[SampleResult],
    control_count: int,
) -> None:
    """Write raw evidence with environment metadata and derived summaries."""

    models_dir = Path(importlib.util.find_spec("rapidocr").origin).parent / "models"
    model_files = sorted(models_dir.glob("*.onnx"))
    payload = {
        "measurement_class": "locally measured",
        "generated_by": "scripts/benchmark_ocr.py",
        "input": str(input_dir.as_posix()),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "opencv": cv2.__version__,
            "onnxruntime": importlib.metadata.version("onnxruntime"),
            "rapidocr": engine.version,
            "execution_provider": "CPUExecutionProvider",
        },
        "artifact": {
            "package_model_bytes": sum(path.stat().st_size for path in model_files),
            "model_files": [path.name for path in model_files],
        },
        "fixture_summary": {
            "labeled_plate_crops": len(
                {(item.fixture, item.plate_index) for item in results}
            ),
            "no_plate_controls": control_count,
            "variants_per_crop": len({item.variant for item in results}),
        },
        "summary": summarize(results),
        "results": [asdict(result) for result in results],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark free local OCR modes on labeled plate crops."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Fixture directory containing ground_truth.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path for retained raw JSON results.",
    )
    args = parser.parse_args(argv)

    try:
        engine = RapidOcrEngine()
        results, control_count = run_benchmark(args.input, engine)
        write_results(args.output, args.input, engine, results, control_count)
    except (BenchmarkError, OSError) as exc:
        safe_message = re.sub(r"[A-Za-z]:[\\/][^\s]+", "<path>", str(exc))
        print(f"OCR benchmark error: {safe_message}", file=sys.stderr)
        return 1

    print(f"Measured {len(results)} OCR sample/variant/candidate combinations.")
    for candidate, values in summarize(results).items():
        print(
            f"{candidate}: {values['exact_matches']}/{values['samples']} exact, "
            f"{values['character_accuracy']:.3f} character accuracy"
        )
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
