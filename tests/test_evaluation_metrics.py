"""Deterministic Phase 7 evaluation-metric tests."""

from __future__ import annotations

import os
import json
import pathlib
import sys

import pytest

_SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from evaluate_system import (  # noqa: E402
    SystemEvaluator,
    calculate_character_accuracy,
    authorization_metrics,
    detection_metrics,
    false_alert_metrics,
    latency_metrics,
    levenshtein_distance,
    match_boxes,
    no_plate_accuracy_metrics,
    nearest_rank_p95,
    ocr_metrics,
    parse_args,
)
from app.repositories.memory import InMemoryAuthorizedVehicleRepository  # noqa: E402


def test_levenshtein_distance_exact_and_different() -> None:
    assert levenshtein_distance("MDY5D3062", "MDY5D3062") == 0
    assert levenshtein_distance("MDY5D3062", "MDY5D3063") == 1
    assert levenshtein_distance("5D3062", "MDY5D3062") == 3
    assert levenshtein_distance("", "") == 0


def test_calculate_character_accuracy_range() -> None:
    assert calculate_character_accuracy("YGN1234", "YGN1234") == 1.0
    assert calculate_character_accuracy("YGN1234", "YGN1235") == pytest.approx(6 / 7)
    assert calculate_character_accuracy("", "YGN1234") == 0.0
    assert calculate_character_accuracy("", "") == 1.0


def test_parse_args_evaluation_defaults() -> None:
    args = parse_args([])
    assert "evaluation" in args.input
    assert "evaluation" in args.output


def test_system_evaluator_runs_and_generates_artifacts(tmp_path: pathlib.Path) -> None:
    input_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "sample-data", "evaluation")
    )
    output_dir = str(tmp_path / "eval_out")
    results = SystemEvaluator(input_dir=input_dir, output_dir=output_dir).evaluate()
    assert "aggregate" in results
    assert "samples" in results
    assert results["aggregate"]["sample_count"] >= 4
    with open(
        os.path.join(output_dir, "evaluation_report.json"), encoding="utf-8"
    ) as handle:
        data = json.load(handle)
    assert data["schema_version"] == "phase7-evaluation-v1"
    with open(
        os.path.join(output_dir, "evaluation_summary.md"), encoding="utf-8"
    ) as handle:
        summary = handle.read()
    assert "# System Evaluation Summary" in summary
    assert "Detection TP / FP / FN" in summary


def test_plate_matching_is_one_to_one_and_threshold_is_inclusive() -> None:
    truth = [(0, 0, 10, 10)]
    predictions = [(0, 0, 10, 10), (0, 0, 10, 10)]
    result = detection_metrics(predictions, truth, 1.0)
    assert result["true_positives"] == 1
    assert result["false_positives"] == 1
    assert result["false_negatives"] == 0
    assert match_boxes([(0, 0, 10, 10)], truth, 1.0)


def test_matching_maximizes_match_count_before_total_iou() -> None:
    truths = [(0, 0, 10, 10), (10, 0, 20, 10)]
    predictions = [(5, 0, 15, 10), (0, 0, 10, 10)]
    matches = match_boxes(predictions, truths, 0.3)
    assert len(matches) == 2
    assert {match["truth_index"] for match in matches} == {0, 1}


def test_matching_and_metrics_are_order_independent_for_multi_plate_inputs() -> None:
    truths = [(0, 0, 10, 10), (20, 0, 30, 10)]
    predictions = [(20, 0, 30, 10), (0, 0, 10, 10)]
    forward = detection_metrics(predictions, truths)
    reverse = detection_metrics(list(reversed(predictions)), list(reversed(truths)))
    assert (
        forward["true_positives"],
        forward["false_positives"],
        forward["false_negatives"],
    ) == (2, 0, 0)
    assert reverse["true_positives"] == forward["true_positives"]


@pytest.mark.parametrize(
    ("predictions", "truths", "precision", "recall"),
    [
        ([], [], 1.0, 1.0),
        ([], [(0, 0, 1, 1)], 1.0, 0.0),
        ([(0, 0, 1, 1)], [], 0.0, 1.0),
    ],
)
def test_zero_denominator_behavior_is_explicit(
    predictions, truths, precision, recall
) -> None:
    result = detection_metrics(predictions, truths)
    assert result["precision"] == precision
    assert result["recall"] == recall


def test_ocr_excludes_no_plate_and_reports_both_character_aggregates() -> None:
    result = ocr_metrics([("YGN1234", "YGN1234"), ("", "")])
    assert result["evaluated_pairs"] == 1
    assert result["exact_matches"] == 1
    assert result["aggregate_character_accuracy"] == 1.0
    assert result["mean_per_plate_character_accuracy"] == 1.0


def test_character_accuracy_uses_truth_length_and_clamps() -> None:
    assert calculate_character_accuracy("YGN1235", "YGN1234") == pytest.approx(6 / 7)
    assert calculate_character_accuracy("", "YGN1234") == 0.0
    assert calculate_character_accuracy("", "") == 1.0


def test_latency_uses_nearest_rank_p95_and_retains_failures() -> None:
    values = [10.0, 20.0, 30.0, 40.0]
    assert nearest_rank_p95(values) == 40.0
    result = latency_metrics(values, failures=2)
    assert result["count"] == 4
    assert result["median_ms"] == 25.0
    assert result["failures"] == 2


def test_false_alert_and_no_plate_denominators_use_negative_images_only() -> None:
    assert false_alert_metrics([False, True, True], [True, True, False]) == {
        "numerator": 1,
        "denominator": 2,
        "rate": 0.5,
    }
    assert no_plate_accuracy_metrics(
        [False, True, True], ["completed", "no_plate_detected", "completed"]
    ) == {
        "numerator": 1,
        "denominator": 2,
        "rate": 0.5,
    }


def test_authorization_metrics_excludes_unlabeled_and_keeps_three_classes() -> None:
    result = authorization_metrics(
        ["AUTHORIZED", "UNAUTHORIZED", "MANUAL_REVIEW", None],
        ["AUTHORIZED", "MANUAL_REVIEW", "MANUAL_REVIEW", None],
    )
    assert result["labeled_count"] == 3
    assert result["accuracy"] == pytest.approx(2 / 3)
    assert set(result["confusion_matrix"]) == {
        "AUTHORIZED",
        "UNAUTHORIZED",
        "MANUAL_REVIEW",
    }


def test_real_evaluator_forces_memory_and_artifact_has_safe_traceability(
    tmp_path: pathlib.Path,
) -> None:
    input_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "sample-data", "evaluation")
    )
    evaluator = SystemEvaluator(input_dir, str(tmp_path / "report"))
    assert isinstance(evaluator.deps.vehicles, InMemoryAuthorizedVehicleRepository)
    first = evaluator._dataset_metadata(
        os.path.join(input_dir, "ground_truth.json"),
        json.loads(
            pathlib.Path(input_dir, "ground_truth.json").read_text(encoding="utf-8")
        ),
    )
    second = evaluator._dataset_metadata(
        os.path.join(input_dir, "ground_truth.json"),
        json.loads(
            pathlib.Path(input_dir, "ground_truth.json").read_text(encoding="utf-8")
        ),
    )
    assert first == second
    report = evaluator.evaluate()
    encoded = json.dumps(report)
    assert "D:\\CVPX" not in encoded
    assert report["dataset"]["independent"] is False
    assert any("not independent" in warning.lower() for warning in report["warnings"])
