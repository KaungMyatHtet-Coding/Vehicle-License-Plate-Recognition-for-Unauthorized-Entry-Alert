"""Reproducible, plate-level evaluation for the local CVPX services.

The bundled four-image set is a development/regression fixture set, not an
independent accuracy evaluation. The evaluator retains raw observations so
aggregate values can be recomputed without rerunning the detector.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import logging
import os
import platform
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Sequence

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.core.config import Settings  # noqa: E402
from app.dependencies import build_application_dependencies  # noqa: E402
from app.services.authorization_decision import AuthorizationDecisionService  # noqa: E402
from app.services.detection_logging import DetectionLoggingService  # noqa: E402
from app.services.ocr_recognition import PlateOcrService  # noqa: E402
from app.services.plate_detection import PlateDetectionService  # noqa: E402
from app.services.recognition_orchestration import (  # noqa: E402
    RecognitionOrchestrationService,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Evaluation] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

ARTIFACT_SCHEMA_VERSION = "phase7-evaluation-v1"
DEFAULT_IOU_THRESHOLD = 0.5


def levenshtein_distance(first: str, second: str) -> int:
    """Return the case-sensitive Levenshtein edit distance."""

    if len(first) < len(second):
        return levenshtein_distance(second, first)
    if not second:
        return len(first)
    previous = list(range(len(second) + 1))
    for index, first_char in enumerate(first):
        current = [index + 1]
        for second_index, second_char in enumerate(second):
            current.append(
                min(
                    previous[second_index + 1] + 1,
                    current[second_index] + 1,
                    previous[second_index] + (first_char != second_char),
                )
            )
        previous = current
    return previous[-1]


def _normalized_text(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())


def calculate_character_accuracy(predicted: str, ground_truth: str) -> float:
    """Per-plate accuracy: clamp ``1 - distance / truth length`` to [0, 1]."""

    predicted = _normalized_text(predicted)
    ground_truth = _normalized_text(ground_truth)
    if not ground_truth:
        return 1.0 if not predicted else 0.0
    distance = levenshtein_distance(predicted, ground_truth)
    return max(0.0, min(1.0, 1.0 - distance / len(ground_truth)))


def _box_tuple(box: Any) -> tuple[int, int, int, int]:
    if isinstance(box, (tuple, list)):
        if len(box) != 4:
            raise ValueError("box must contain four coordinates")
        return tuple(int(value) for value in box)  # type: ignore[return-value]
    if isinstance(box, dict):
        return tuple(int(box[key]) for key in ("x1", "y1", "x2", "y2"))  # type: ignore[return-value]
    return tuple(int(getattr(box, key)) for key in ("x1", "y1", "x2", "y2"))  # type: ignore[return-value]


def intersection_over_union(
    first: tuple[int, int, int, int], second: tuple[int, int, int, int]
) -> float:
    """Compute IoU for exclusive-edge integer boxes."""

    x1 = max(first[0], second[0])
    y1 = max(first[1], second[1])
    x2 = min(first[2], second[2])
    y2 = min(first[3], second[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    first_area = max(0, first[2] - first[0]) * max(0, first[3] - first[1])
    second_area = max(0, second[2] - second[0]) * max(0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0


def match_boxes(
    predictions: Sequence[Any],
    truths: Sequence[Any],
    iou_threshold: float = DEFAULT_IOU_THRESHOLD,
) -> list[dict[str, float | int]]:
    """Deterministically maximize match count, then total IoU.

    Predictions and truths are canonically ordered before dynamic programming,
    making the result independent of detector or manifest order. Returned
    indexes refer to the original input sequences.
    """

    if not 0.0 <= iou_threshold <= 1.0:
        raise ValueError("IoU threshold must be between zero and one")
    prediction_boxes = [_box_tuple(item) for item in predictions]
    truth_boxes = [_box_tuple(item) for item in truths]
    prediction_order = sorted(
        range(len(prediction_boxes)), key=lambda i: prediction_boxes[i]
    )
    truth_order = sorted(range(len(truth_boxes)), key=lambda i: truth_boxes[i])
    scores = [
        [
            intersection_over_union(prediction_boxes[p], truth_boxes[t])
            for t in truth_order
        ]
        for p in prediction_order
    ]
    memo: dict[tuple[int, int], tuple[int, float, tuple[int, ...]]] = {}

    def better(
        left: tuple[int, float, tuple[int, ...]],
        right: tuple[int, float, tuple[int, ...]],
    ) -> tuple[int, float, tuple[int, ...]]:
        if left[0] != right[0]:
            return left if left[0] > right[0] else right
        if abs(left[1] - right[1]) > 1e-12:
            return left if left[1] > right[1] else right
        return left if left[2] < right[2] else right

    def solve(pred_index: int, used_truths: int) -> tuple[int, float, tuple[int, ...]]:
        key = (pred_index, used_truths)
        if key in memo:
            return memo[key]
        if pred_index == len(prediction_order):
            result = (0, 0.0, ())
        else:
            skipped = solve(pred_index + 1, used_truths)
            result = (skipped[0], skipped[1], (-1,) + skipped[2])
            for truth_index, score in enumerate(scores[pred_index]):
                if used_truths & (1 << truth_index) or score < iou_threshold:
                    continue
                tail = solve(pred_index + 1, used_truths | (1 << truth_index))
                candidate = (tail[0] + 1, tail[1] + score, (truth_index,) + tail[2])
                result = better(result, candidate)
        memo[key] = result
        return result

    assignment = solve(0, 0)[2]
    matches: list[dict[str, float | int]] = []
    for sorted_prediction, sorted_truth in enumerate(assignment):
        if sorted_truth >= 0:
            original_prediction = prediction_order[sorted_prediction]
            original_truth = truth_order[sorted_truth]
            matches.append(
                {
                    "prediction_index": original_prediction,
                    "truth_index": original_truth,
                    "iou": round(scores[sorted_prediction][sorted_truth], 6),
                }
            )
    return sorted(
        matches,
        key=lambda item: (int(item["prediction_index"]), int(item["truth_index"])),
    )


def detection_metrics(
    predictions: Sequence[Any],
    truths: Sequence[Any],
    iou_threshold: float = DEFAULT_IOU_THRESHOLD,
) -> dict[str, Any]:
    """Return plate-level TP/FP/FN and explicit zero-denominator ratios."""

    matches = match_boxes(predictions, truths, iou_threshold)
    true_positive = len(matches)
    false_positive = len(predictions) - true_positive
    false_negative = len(truths) - true_positive
    precision = true_positive / len(predictions) if predictions else 1.0
    recall = true_positive / len(truths) if truths else 1.0
    return {
        "true_positives": true_positive,
        "false_positives": false_positive,
        "false_negatives": false_negative,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "iou_threshold": iou_threshold,
        "matches": matches,
    }


def ocr_metrics(pairs: Sequence[tuple[str, str]]) -> dict[str, Any]:
    """Compute OCR values only from valid matched positive plate pairs."""

    valid = [
        (_normalized_text(predicted), _normalized_text(truth))
        for predicted, truth in pairs
    ]
    valid = [(predicted, truth) for predicted, truth in valid if truth]
    exact_matches = sum(predicted == truth for predicted, truth in valid)
    distances = [levenshtein_distance(predicted, truth) for predicted, truth in valid]
    truth_characters = sum(len(truth) for _, truth in valid)
    aggregate_accuracy = (
        max(0.0, min(1.0, 1.0 - sum(distances) / truth_characters))
        if truth_characters
        else 0.0
    )
    per_plate = [
        calculate_character_accuracy(predicted, truth) for predicted, truth in valid
    ]
    return {
        "exact_matches": exact_matches,
        "evaluated_pairs": len(valid),
        "exact_match_rate": exact_matches / len(valid) if valid else 0.0,
        "total_edit_distance": sum(distances),
        "total_ground_truth_characters": truth_characters,
        "aggregate_character_accuracy": aggregate_accuracy,
        "mean_per_plate_character_accuracy": statistics.fmean(per_plate)
        if per_plate
        else 0.0,
        "empty_text_behavior": "empty ground truth is excluded; empty prediction scores zero for non-empty truth",
    }


def nearest_rank_p95(values: Sequence[float]) -> float:
    """Return nearest-rank p95, with an empty series represented as zero."""

    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, (95 * len(ordered) + 99) // 100 - 1))
    return ordered[index]


def latency_metrics(values: Sequence[float], failures: int = 0) -> dict[str, Any]:
    """Return count, mean, median, nearest-rank p95, max, and failures."""

    return {
        "count": len(values),
        "mean_ms": statistics.fmean(values) if values else 0.0,
        "median_ms": statistics.median(values) if values else 0.0,
        "p95_ms": nearest_rank_p95(values),
        "max_ms": max(values) if values else 0.0,
        "failures": failures,
    }


def false_alert_metrics(
    negative_flags: Sequence[bool], unauthorized_flags: Sequence[bool]
) -> dict[str, float | int]:
    """Use only negative/no-plate images as the false-alert denominator."""

    numerator = sum(
        1
        for is_negative, unauthorized in zip(negative_flags, unauthorized_flags)
        if is_negative and unauthorized
    )
    denominator = sum(1 for is_negative in negative_flags if is_negative)
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": numerator / denominator if denominator else 0.0,
    }


def no_plate_accuracy_metrics(
    negative_flags: Sequence[bool], statuses: Sequence[str]
) -> dict[str, float | int]:
    """Measure correct no-plate workflow status only on negative images."""

    numerator = sum(
        1
        for is_negative, status in zip(negative_flags, statuses)
        if is_negative and status == "no_plate_detected"
    )
    denominator = sum(1 for is_negative in negative_flags if is_negative)
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": numerator / denominator if denominator else 0.0,
    }


def authorization_metrics(
    decisions: Sequence[str | None], expected: Sequence[str | None]
) -> dict[str, Any]:
    """Exclude unlabeled decisions and retain the three-class confusion matrix."""

    classes = ("AUTHORIZED", "UNAUTHORIZED", "MANUAL_REVIEW")
    matrix = {decision: {label: 0 for label in classes} for decision in classes}
    labeled = 0
    for actual, target in zip(decisions, expected):
        if actual in matrix and target in classes:
            labeled += 1
            matrix[actual][target] += 1
    correct = sum(matrix[label][label] for label in classes)
    return {
        "labeled_count": labeled,
        "accuracy": correct / labeled if labeled else 0.0,
        "confusion_matrix": matrix,
    }


@dataclass
class SampleMetric:
    file: str
    expected_detections: int
    predicted_detections: int
    ground_truth_boxes: list[dict[str, Any]]
    predicted_boxes: list[dict[str, Any]]
    matches: list[dict[str, float | int]]
    ocr_pairs: list[dict[str, str]]
    decision: str | None
    expected_decision: str | None
    status: str
    timing_ms: float | None
    error: str | None = None


def _safe_error(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    return str(code) if isinstance(code, str) and code else type(exc).__name__


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SystemEvaluator:
    """Run actual detector/OCR/decision services without mock substitution."""

    def __init__(
        self,
        input_dir: str,
        output_dir: str,
        iou_threshold: float = DEFAULT_IOU_THRESHOLD,
    ) -> None:
        self.input_dir = os.path.abspath(input_dir)
        self.output_dir = os.path.abspath(output_dir)
        self.iou_threshold = iou_threshold
        model_path = (
            Path(__file__).resolve().parents[1] / "models" / "day4" / "best.onnx"
        )
        self.settings = Settings(
            _env_file=None,
            repository_mode="memory",
            app_mode="localhost",
            DETECTOR_MODEL_PATH=model_path if model_path.is_file() else None,
        )
        self.deps = build_application_dependencies(self.settings)

    def _build_pipeline(self) -> RecognitionOrchestrationService:
        return RecognitionOrchestrationService(
            detector=PlateDetectionService(self.settings),
            ocr=PlateOcrService(self.settings),
            decision=AuthorizationDecisionService(self.deps.vehicles, self.settings),
            logging=DetectionLoggingService(
                self.deps.detection_logs, self.deps.evidence_storage, self.settings
            ),
            activity=self.deps.recognition_activity,
            settings=self.settings,
        )

    def _dataset_metadata(
        self, gt_path: str, gt_data: list[dict[str, Any]]
    ) -> dict[str, Any]:
        manifest_hash = hashlib.sha256()
        manifest_hash.update(open(gt_path, "rb").read())
        for item in gt_data:
            path = os.path.join(self.input_dir, item["file"])
            if os.path.isfile(path):
                manifest_hash.update(item["file"].encode())
                manifest_hash.update(bytes.fromhex(_sha256_file(path)))
        return {
            "identifier": "cvpx-project-generated-evaluation-fixtures",
            "manifest_sha256": manifest_hash.hexdigest(),
            "version": "ground_truth-v1",
            "independent": False,
        }

    def evaluate(self) -> dict[str, Any]:
        gt_path = os.path.join(self.input_dir, "ground_truth.json")
        if not os.path.isfile(gt_path):
            raise FileNotFoundError("Ground truth file not found")
        with open(gt_path, encoding="utf-8") as handle:
            gt_data: list[dict[str, Any]] = json.load(handle)

        pipeline = self._build_pipeline()
        samples: list[SampleMetric] = []
        timings: list[float] = []
        cold_latency: float | None = None
        failures = 0
        detection_totals = {
            "true_positives": 0,
            "false_positives": 0,
            "false_negatives": 0,
        }
        ocr_pairs: list[tuple[str, str]] = []
        negative_flags: list[bool] = []
        unauthorized_flags: list[bool] = []
        statuses: list[str] = []
        decisions: list[str | None] = []
        expected_decisions: list[str | None] = []

        for index, item in enumerate(gt_data, 1):
            file_name = str(item["file"])
            expected_boxes = list(item.get("bounding_boxes", []))
            expected_count = int(item.get("expected_detections", len(expected_boxes)))
            expected_decision = item.get("expected_decision")
            negative_flags.append(expected_count == 0)
            image_path = os.path.join(self.input_dir, file_name)
            if not os.path.isfile(image_path):
                failures += 1
                samples.append(
                    SampleMetric(
                        file_name,
                        expected_count,
                        0,
                        expected_boxes,
                        [],
                        [],
                        [],
                        None,
                        expected_decision,
                        "error",
                        None,
                        "FILE_NOT_FOUND",
                    )
                )
                unauthorized_flags.append(False)
                statuses.append("error")
                decisions.append(None)
                expected_decisions.append(expected_decision)
                continue
            started = time.perf_counter()
            try:
                with open(image_path, "rb") as handle:
                    image_bytes = handle.read()
                analysis = pipeline.analyze(image_bytes, f"eval-sample-{index}")
                elapsed = round((time.perf_counter() - started) * 1000, 3)
                if cold_latency is None:
                    cold_latency = elapsed
                timings.append(elapsed)
                predictions = sorted(
                    [
                        {
                            "x1": detection.bbox.x1,
                            "y1": detection.bbox.y1,
                            "x2": detection.bbox.x2,
                            "y2": detection.bbox.y2,
                            "confidence": detection.confidence,
                        }
                        for detection in analysis.detection.detections
                    ],
                    key=lambda item: (
                        item["x1"],
                        item["y1"],
                        item["x2"],
                        item["y2"],
                        -item["confidence"],
                    ),
                )
                matches = match_boxes(predictions, expected_boxes, self.iou_threshold)
                for key in detection_totals:
                    detection_totals[key] += detection_metrics(
                        predictions, expected_boxes, self.iou_threshold
                    )[key]
                selected_bbox = (
                    _box_tuple(analysis.selected.bbox)
                    if analysis.selected is not None
                    else None
                )
                pairs: list[dict[str, str]] = []
                if analysis.ocr is not None and selected_bbox is not None:
                    for match in matches:
                        if (
                            _box_tuple(predictions[int(match["prediction_index"])])
                            == selected_bbox
                        ):
                            truth = expected_boxes[int(match["truth_index"])].get(
                                "text", ""
                            )
                            pair = {
                                "predicted": analysis.ocr.normalized_text,
                                "ground_truth": str(truth),
                            }
                            pairs.append(pair)
                            ocr_pairs.append((pair["predicted"], pair["ground_truth"]))
                            break
                decision = getattr(analysis.decision, "decision", None)
                unauthorized_flags.append(decision == "UNAUTHORIZED")
                statuses.append(analysis.detection.status)
                decisions.append(decision)
                expected_decisions.append(expected_decision)
                samples.append(
                    SampleMetric(
                        file_name,
                        expected_count,
                        len(predictions),
                        expected_boxes,
                        predictions,
                        matches,
                        pairs,
                        decision,
                        expected_decision,
                        analysis.detection.status,
                        elapsed,
                    )
                )
            except Exception as exc:
                failures += 1
                elapsed = round((time.perf_counter() - started) * 1000, 3)
                samples.append(
                    SampleMetric(
                        file_name,
                        expected_count,
                        0,
                        expected_boxes,
                        [],
                        [],
                        [],
                        None,
                        expected_decision,
                        "error",
                        elapsed,
                        _safe_error(exc),
                    )
                )
                unauthorized_flags.append(False)
                statuses.append("error")
                decisions.append(None)
                expected_decisions.append(expected_decision)

        # Per-image matching totals are authoritative for plate-level metrics.
        ocr_aggregate = ocr_metrics(ocr_pairs)
        false_alert = false_alert_metrics(negative_flags, unauthorized_flags)
        no_plate_accuracy = no_plate_accuracy_metrics(negative_flags, statuses)
        authorization = authorization_metrics(decisions, expected_decisions)
        aggregate = {
            "detection": detection_totals
            | {
                "precision": detection_totals["true_positives"]
                / (
                    detection_totals["true_positives"]
                    + detection_totals["false_positives"]
                )
                if detection_totals["true_positives"]
                + detection_totals["false_positives"]
                else 1.0,
                "recall": detection_totals["true_positives"]
                / (
                    detection_totals["true_positives"]
                    + detection_totals["false_negatives"]
                )
                if detection_totals["true_positives"]
                + detection_totals["false_negatives"]
                else 1.0,
                "iou_threshold": self.iou_threshold,
            },
            "ocr": ocr_aggregate,
            "false_alert": false_alert,
            "no_plate_accuracy": no_plate_accuracy,
            "authorization": authorization,
            "latency": latency_metrics(timings, failures)
            | {
                "cold_first_sample_ms": cold_latency,
                "warm_samples": max(0, len(timings) - 1),
            },
            "sample_count": len(samples),
            "total_expected_plates": sum(
                sample.expected_detections for sample in samples
            ),
        }
        dataset = self._dataset_metadata(gt_path, gt_data)
        model_path = self.settings.detector_model_path
        environment = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "runtime": sys.implementation.name,
            "hardware": platform.machine(),
            "model_path_identifier": model_path.name if model_path else None,
            "model_sha256": _sha256_file(str(model_path))
            if model_path and model_path.is_file()
            else None,
            "ocr_version": _package_version("rapidocr"),
        }
        report = {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset": dataset,
            "sample_counts": {
                "images": len(samples),
                "positive_images": sum(
                    sample.expected_detections > 0 for sample in samples
                ),
                "negative_no_plate_images": sum(negative_flags),
                "labeled_plate_instances": aggregate["total_expected_plates"],
            },
            "aggregate": aggregate,
            "samples": [asdict(sample) for sample in samples],
            "warnings": [
                "Development/regression fixtures only; not independent.",
                "Four images are insufficient for real-world accuracy or reliable p95 claims.",
                "The recognition pipeline exposes one selected OCR result; unmatched multi-plate OCR pairs are not inferred.",
            ],
            "limitations": [
                "No real-world or Myanmar-specific performance claim.",
                "No-plate status is a workflow status, not an authorization class.",
                "Failures are retained and excluded from successful latency aggregates.",
            ],
            "environment": environment,
        }
        os.makedirs(self.output_dir, exist_ok=True)
        with open(
            os.path.join(self.output_dir, "evaluation_report.json"),
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(report, handle, indent=2)
        with open(
            os.path.join(self.output_dir, "evaluation_summary.md"),
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write(_summary_markdown(report))
        return report


def _package_version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def _summary_markdown(report: dict[str, Any]) -> str:
    detection = report["aggregate"]["detection"]
    ocr = report["aggregate"]["ocr"]
    latency = report["aggregate"]["latency"]
    return "\n".join(
        [
            "# System Evaluation Summary — Phase 7",
            "",
            "**Classification:** development/regression fixtures only; not independent evaluation.",
            f"**Schema:** `{report['schema_version']}`",
            f"**Images:** {report['sample_counts']['images']} ({report['sample_counts']['positive_images']} positive, {report['sample_counts']['negative_no_plate_images']} negative)",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| Detection TP / FP / FN | {detection['true_positives']} / {detection['false_positives']} / {detection['false_negatives']} |",
            f"| Detection precision / recall | {detection['precision']:.4f} / {detection['recall']:.4f} |",
            f"| OCR exact matches / evaluated pairs | {ocr['exact_matches']} / {ocr['evaluated_pairs']} |",
            f"| False alerts / negative images | {report['aggregate']['false_alert']['numerator']} / {report['aggregate']['false_alert']['denominator']} |",
            f"| Latency count / mean / median / p95 / max | {latency['count']} / {latency['mean_ms']:.2f} / {latency['median_ms']:.2f} / {latency['p95_ms']:.2f} / {latency['max_ms']:.2f} ms |",
            "",
            "No values above support real-world accuracy claims.",
            "",
        ]
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="evaluate_system.py")
    parser.add_argument("--input", default=os.path.join("sample-data", "evaluation"))
    parser.add_argument("--output", default=os.path.join("artifacts", "evaluation"))
    parser.add_argument("--iou-threshold", type=float, default=DEFAULT_IOU_THRESHOLD)
    args = parser.parse_args(argv)
    if not 0.0 <= args.iou_threshold <= 1.0:
        parser.error("--iou-threshold must be between zero and one")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        SystemEvaluator(args.input, args.output, args.iou_threshold).evaluate()
        return 0
    except Exception as exc:
        logger.error("Evaluation failed: %s", _safe_error(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
