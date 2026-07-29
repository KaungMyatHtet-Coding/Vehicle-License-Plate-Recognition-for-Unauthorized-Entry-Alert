"""Focused Day 7 OCR benchmark contract and honesty tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from benchmark_ocr import (  # noqa: E402
    BenchmarkError,
    CANDIDATES,
    build_variants,
    character_score,
    load_labeled_crops,
    normalize_plate_text,
    run_benchmark,
    summarize,
    write_results,
)

EVALUATION_DIR = Path(__file__).resolve().parent.parent / "sample-data" / "evaluation"


class FakeEngine:
    version = "test"

    def recognize(self, image: np.ndarray, candidate: str) -> tuple[str, float | None]:
        assert candidate in CANDIDATES
        assert image.dtype == np.uint8
        return "ygn 5a 1234", 0.75


def test_text_normalization_and_character_score_are_deterministic() -> None:
    assert normalize_plate_text(" ygn 5a_1234! ") == "YGN5A1234"
    assert character_score("ABC123", "ABC023") == (5, 6)
    assert character_score("ABC", "ABCZZ") == (1, 3)


def test_manifest_loads_four_copied_labeled_crops_and_control() -> None:
    crops, controls = load_labeled_crops(EVALUATION_DIR)

    assert len(crops) == 4
    assert controls == 1
    assert {crop.expected_text for crop in crops} == {
        "YGN 5A-1234",
        "MDY 3B-5678",
        "SGN 1C-9012",
        "NPT 2D-3456",
    }
    assert all(crop.image.flags.owndata for crop in crops)


def test_invalid_or_unlabeled_manifest_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "ground_truth.json").write_text(
        json.dumps(
            [
                {
                    "file": "fixture.png",
                    "expected_detections": 1,
                    "bounding_boxes": [{"x1": 0, "y1": 0, "x2": 5, "y2": 5}],
                }
            ]
        ),
        encoding="utf-8",
    )
    cv2.imwrite(str(tmp_path / "fixture.png"), np.zeros((10, 10, 3), np.uint8))

    with pytest.raises(BenchmarkError, match="contain text"):
        load_labeled_crops(tmp_path)


def test_variants_use_day6_independent_contract_without_mutation() -> None:
    crop = np.arange(40 * 120 * 3, dtype=np.uint8).reshape((40, 120, 3))
    original = crop.copy()

    variants = build_variants(crop)

    assert tuple(variants) == (
        "original",
        "grayscale",
        "resize",
        "denoise",
        "contrast",
        "threshold",
    )
    assert np.array_equal(crop, original)
    assert variants["original"] is not crop
    assert variants["resize"].shape == (107, 320, 3)


def test_raw_results_drive_summary_without_fabricated_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crop = np.zeros((12, 24, 3), dtype=np.uint8)
    monkeypatch.setattr(
        "benchmark_ocr.load_labeled_crops",
        lambda _: (
            [
                type(
                    "Crop",
                    (),
                    {
                        "fixture": "fixture.png",
                        "plate_index": 0,
                        "expected_text": "YGN 5A-1234",
                        "image": crop,
                    },
                )()
            ],
            0,
        ),
    )

    results, controls = run_benchmark(Path("."), FakeEngine())
    summary = summarize(results)

    assert controls == 0
    assert len(results) == 12
    assert all(result.confidence == 0.75 for result in results)
    assert all(result.raw_text == "ygn 5a 1234" for result in results)
    assert all(not result.exact_match for result in results)
    assert summary["rapidocr_recognition_only"]["samples"] == 6
    assert summary["rapidocr_recognition_only"]["exact_matches"] == 0


def test_output_retains_environment_raw_samples_and_controls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "benchmark_ocr.importlib.util.find_spec",
        lambda _: type(
            "Spec", (), {"origin": str(tmp_path / "rapidocr/__init__.py")}
        )(),
    )
    (tmp_path / "rapidocr/models").mkdir(parents=True)
    (tmp_path / "rapidocr/models/model.onnx").write_bytes(b"model")
    results, controls = run_benchmark(EVALUATION_DIR, FakeEngine())
    output = tmp_path / "raw.json"

    write_results(output, EVALUATION_DIR, FakeEngine(), results, controls)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["measurement_class"] == "locally measured"
    assert payload["environment"]["execution_provider"] == "CPUExecutionProvider"
    assert payload["fixture_summary"]["labeled_plate_crops"] == 4
    assert payload["fixture_summary"]["no_plate_controls"] == 1
    assert payload["artifact"]["package_model_bytes"] == 5
    assert len(payload["results"]) == 48
