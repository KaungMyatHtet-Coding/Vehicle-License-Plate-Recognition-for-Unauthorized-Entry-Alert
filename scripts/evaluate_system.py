"""Day 20 System Evaluation Runner.

Calculates reproducible quality, accuracy, false-alert, and latency metrics
against ground-truth datasets and saves traceable evaluation artifacts.

Usage:
    python scripts/evaluate_system.py --input sample-data/evaluation --output artifacts/evaluation
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any, Sequence

# ---------------------------------------------------------------------------
# Add backend to path so we can import app services without installing.
# ---------------------------------------------------------------------------
_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


from app.core.config import get_settings  # noqa: E402
from app.dependencies import get_application_dependencies  # noqa: E402
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


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def calculate_character_accuracy(predicted: str, ground_truth: str) -> float:
    """Calculate character-level accuracy percentage between predicted and truth."""
    if not predicted and not ground_truth:
        return 1.0
    if not predicted or not ground_truth:
        return 0.0
    max_len = max(len(predicted), len(ground_truth))
    dist = levenshtein_distance(predicted.upper(), ground_truth.upper())
    return max(0.0, 1.0 - (dist / max_len))


@dataclass
class SampleMetric:
    file: str
    expected_detections: int
    detected_count: int
    detection_hit: bool
    expected_texts: list[str]
    predicted_texts: list[str]
    ocr_exact_match: bool
    character_accuracy: float
    total_ms: float
    status: str
    error: str | None = None


@dataclass
class AggregateMetrics:
    total_samples: int
    total_expected_plates: int
    total_detected_plates: int
    detection_recall: float
    detection_precision: float
    ocr_exact_match_rate: float
    mean_character_accuracy: float
    mean_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    false_alert_count: int
    false_alert_rate: float


class SystemEvaluator:
    """Runs end-to-end evaluation against ground truth JSON dataset."""

    def __init__(self, input_dir: str, output_dir: str) -> None:
        self.input_dir = os.path.abspath(input_dir)
        self.output_dir = os.path.abspath(output_dir)
        self.settings = get_settings()
        self.deps = get_application_dependencies()

    def _build_pipeline(self) -> RecognitionOrchestrationService:
        detector = PlateDetectionService(self.settings)
        ocr = PlateOcrService(self.settings)
        decision = AuthorizationDecisionService(self.deps.vehicles, self.settings)
        logging_svc = DetectionLoggingService(
            self.deps.detection_logs, self.deps.evidence_storage, self.settings
        )
        return RecognitionOrchestrationService(
            detector=detector,
            ocr=ocr,
            decision=decision,
            logging=logging_svc,
            activity=self.deps.recognition_activity,
        )

    def evaluate(self) -> dict[str, Any]:
        gt_path = os.path.join(self.input_dir, "ground_truth.json")
        if not os.path.isfile(gt_path):
            raise FileNotFoundError(f"Ground truth file not found: {gt_path}")

        with open(gt_path, encoding="utf-8") as f:
            gt_data: list[dict[str, Any]] = json.load(f)

        orch = self._build_pipeline()
        sample_results: list[SampleMetric] = []
        latencies: list[float] = []

        total_expected_plates = 0
        total_detected_plates = 0
        correct_detections = 0
        exact_ocr_matches = 0
        char_accuracies: list[float] = []
        false_alerts = 0

        logger.info("Evaluating %d samples from %s...", len(gt_data), self.input_dir)

        for idx, item in enumerate(gt_data, 1):
            file_name = item["file"]
            img_path = os.path.join(self.input_dir, file_name)
            expected_count = item.get("expected_detections", 0)
            expected_boxes = item.get("bounding_boxes", [])
            expected_texts = [box["text"] for box in expected_boxes]

            total_expected_plates += expected_count

            if not os.path.isfile(img_path):
                logger.warning("Sample image missing: %s", img_path)
                sample_results.append(
                    SampleMetric(
                        file=file_name,
                        expected_detections=expected_count,
                        detected_count=0,
                        detection_hit=False,
                        expected_texts=expected_texts,
                        predicted_texts=[],
                        ocr_exact_match=False,
                        character_accuracy=0.0,
                        total_ms=0.0,
                        status="error",
                        error="File not found",
                    )
                )
                continue

            with open(img_path, "rb") as f:
                img_bytes = f.read()

            t0 = time.perf_counter()
            cid = f"eval-sample-{idx}"
            try:
                res = orch.recognize(img_bytes, cid)
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
                latencies.append(elapsed_ms)

                detected_count = res.detection_count
                total_detected_plates += detected_count

                hit = (expected_count == 0 and detected_count == 0) or (
                    expected_count > 0 and detected_count > 0
                )
                if hit:
                    correct_detections += 1

                pred_texts: list[str] = []
                if res.ocr and res.ocr.normalized_text:
                    pred_texts.append(res.ocr.normalized_text)

                # Evaluate OCR
                if expected_texts:
                    import re

                    target_norm = re.sub(r"[^A-Za-z0-9]", "", expected_texts[0]).upper()
                    pred_norm = (
                        re.sub(r"[^A-Za-z0-9]", "", pred_texts[0]).upper()
                        if pred_texts
                        else ""
                    )
                    exact = pred_norm == target_norm
                    char_acc = calculate_character_accuracy(pred_norm, target_norm)
                else:
                    exact = len(pred_texts) == 0
                    char_acc = 1.0 if exact else 0.0

                if exact:
                    exact_ocr_matches += 1
                char_accuracies.append(char_acc)

                # False alert check (unexpected plate detected on non-plate image)
                if expected_count == 0 and detected_count > 0:
                    false_alerts += 1

                sample_results.append(
                    SampleMetric(
                        file=file_name,
                        expected_detections=expected_count,
                        detected_count=detected_count,
                        detection_hit=hit,
                        expected_texts=expected_texts,
                        predicted_texts=pred_texts,
                        ocr_exact_match=exact,
                        character_accuracy=char_acc,
                        total_ms=elapsed_ms,
                        status=res.status,
                        error=None,
                    )
                )
                logger.info(
                    "[%d/%d] %s: detected=%d expected=%d latency=%.1fms",
                    idx,
                    len(gt_data),
                    file_name,
                    detected_count,
                    expected_count,
                    elapsed_ms,
                )

            except Exception as exc:
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
                logger.error("Error evaluating %s: %s", file_name, exc)
                sample_results.append(
                    SampleMetric(
                        file=file_name,
                        expected_detections=expected_count,
                        detected_count=0,
                        detection_hit=False,
                        expected_texts=expected_texts,
                        predicted_texts=[],
                        ocr_exact_match=False,
                        character_accuracy=0.0,
                        total_ms=elapsed_ms,
                        status="error",
                        error=str(exc),
                    )
                )

        # Aggregate calculations
        n_samples = len(sample_results)
        mean_lat = sum(latencies) / len(latencies) if latencies else 0.0
        min_lat = min(latencies) if latencies else 0.0
        max_lat = max(latencies) if latencies else 0.0

        rec = correct_detections / n_samples if n_samples > 0 else 0.0
        prec = (
            correct_detections / total_detected_plates
            if total_detected_plates > 0
            else 1.0
        )
        exact_rate = exact_ocr_matches / n_samples if n_samples > 0 else 0.0
        mean_char_acc = (
            sum(char_accuracies) / len(char_accuracies) if char_accuracies else 0.0
        )
        false_alert_rate = false_alerts / n_samples if n_samples > 0 else 0.0

        aggregate = AggregateMetrics(
            total_samples=n_samples,
            total_expected_plates=total_expected_plates,
            total_detected_plates=total_detected_plates,
            detection_recall=round(rec, 4),
            detection_precision=round(prec, 4),
            ocr_exact_match_rate=round(exact_rate, 4),
            mean_character_accuracy=round(mean_char_acc, 4),
            mean_latency_ms=round(mean_lat, 2),
            min_latency_ms=round(min_lat, 2),
            max_latency_ms=round(max_lat, 2),
            false_alert_count=false_alerts,
            false_alert_rate=round(false_alert_rate, 4),
        )

        os.makedirs(self.output_dir, exist_ok=True)

        report_json_path = os.path.join(self.output_dir, "evaluation_report.json")
        summary_md_path = os.path.join(self.output_dir, "evaluation_summary.md")

        full_output = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "environment": {
                "python": sys.version.split()[0],
                "platform": sys.platform,
                "detector_model": str(self.settings.detector_model_path),
            },
            "aggregate": asdict(aggregate),
            "samples": [asdict(s) for s in sample_results],
        }

        with open(report_json_path, "w", encoding="utf-8") as f:
            json.dump(full_output, f, indent=2)

        # Generate summary markdown
        md_lines = [
            "# System Evaluation Summary — Day 20",
            "",
            f"**Timestamp:** {full_output['timestamp']}",
            f"**Total Samples Evaluated:** {aggregate.total_samples}",
            "",
            "## Key Performance Indicators (KPIs)",
            "",
            "| Metric | Value | Target |",
            "|---|---|---|",
            f"| **Detection Recall** | {aggregate.detection_recall * 100:.1f}% | ≥ 90.0% |",
            f"| **Detection Precision** | {aggregate.detection_precision * 100:.1f}% | ≥ 90.0% |",
            f"| **OCR Exact Match Rate** | {aggregate.ocr_exact_match_rate * 100:.1f}% | ≥ 80.0% |",
            f"| **Mean Character Accuracy** | {aggregate.mean_character_accuracy * 100:.1f}% | ≥ 85.0% |",
            f"| **False Alert Rate** | {aggregate.false_alert_rate * 100:.1f}% | ≤ 5.0% |",
            f"| **Mean Latency** | {aggregate.mean_latency_ms:.1f} ms | ≤ 2000 ms |",
            "",
            "## Latency Distribution",
            "",
            f"- **Min:** {aggregate.min_latency_ms:.1f} ms",
            f"- **Mean:** {aggregate.mean_latency_ms:.1f} ms",
            f"- **Max:** {aggregate.max_latency_ms:.1f} ms",
            "",
            "## Detailed Sample Results",
            "",
            "| File | Expected | Detected | OCR Result | Match | Latency (ms) |",
            "|---|---|---|---|---|---|",
        ]
        for s in sample_results:
            pred_str = s.predicted_texts[0] if s.predicted_texts else "-"
            match_str = "✅" if s.ocr_exact_match else "❌"
            md_lines.append(
                f"| `{s.file}` | {s.expected_detections} | {s.detected_count} | `{pred_str}` | {match_str} | {s.total_ms:.1f} |"
            )

        with open(summary_md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines) + "\n")

        logger.info("Evaluation report saved to: %s", report_json_path)
        logger.info("Evaluation summary saved to: %s", summary_md_path)

        return full_output


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="evaluate_system.py",
        description="Day 20 System Evaluation Runner — reproducible accuracy & timing evaluation.",
    )
    parser.add_argument(
        "--input",
        type=str,
        default=os.path.join("sample-data", "evaluation"),
        help="Path to evaluation dataset directory containing ground_truth.json",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=os.path.join("artifacts", "evaluation"),
        help="Path to directory where evaluation JSON and Markdown reports will be saved",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    evaluator = SystemEvaluator(input_dir=args.input, output_dir=args.output)
    try:
        evaluator.evaluate()
        return 0
    except Exception as exc:
        logger.error("Evaluation failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
