"""Day 20 tests for system evaluation metrics, Levenshtein distance, and report generation."""

from __future__ import annotations

import json
import os
import pathlib
import sys

# Add scripts/ and backend/ to path
_SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
for _p in (_SCRIPTS, _BACKEND):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from evaluate_system import (  # noqa: E402
    SystemEvaluator,
    calculate_character_accuracy,
    levenshtein_distance,
    parse_args,
)


def test_levenshtein_distance_exact_and_different() -> None:
    """levenshtein_distance computes correct edit distance."""
    assert levenshtein_distance("MDY5D3062", "MDY5D3062") == 0
    assert levenshtein_distance("MDY5D3062", "MDY5D3063") == 1
    assert levenshtein_distance("5D3062", "MDY5D3062") == 3
    assert levenshtein_distance("", "") == 0


def test_calculate_character_accuracy_range() -> None:
    """calculate_character_accuracy returns a float between 0.0 and 1.0."""
    assert calculate_character_accuracy("YGN1234", "YGN1234") == 1.0
    assert calculate_character_accuracy("YGN1234", "YGN1235") == pytest.approx(6 / 7)
    assert calculate_character_accuracy("", "YGN1234") == 0.0
    assert calculate_character_accuracy("", "") == 1.0


def test_parse_args_evaluation_defaults() -> None:
    """parse_args accepts default input and output path locations."""
    args = parse_args([])
    assert "evaluation" in args.input
    assert "evaluation" in args.output


def test_system_evaluator_runs_and_generates_artifacts(tmp_path: pathlib.Path) -> None:
    """SystemEvaluator generates valid evaluation_report.json and evaluation_summary.md."""
    input_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "sample-data", "evaluation")
    )
    output_dir = str(tmp_path / "eval_out")

    evaluator = SystemEvaluator(input_dir=input_dir, output_dir=output_dir)
    results = evaluator.evaluate()

    assert "aggregate" in results
    assert "samples" in results
    assert results["aggregate"]["total_samples"] >= 4

    # Verify JSON artifact
    json_path = os.path.join(output_dir, "evaluation_report.json")
    assert os.path.isfile(json_path)
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["aggregate"]["detection_recall"] >= 0.0

    # Verify Markdown summary artifact
    md_path = os.path.join(output_dir, "evaluation_summary.md")
    assert os.path.isfile(md_path)
    with open(md_path, encoding="utf-8") as f:
        md_content = f.read()
    assert "# System Evaluation Summary" in md_content
    assert "Detection Recall" in md_content
