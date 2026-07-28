"""Benchmark Day 4 detector candidates against generated fixtures.

This is a research harness, not the Day 5 backend detector integration.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import platform
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import onnxruntime as ort

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.detection_contract import (  # noqa: E402
    PlateDetection,
    validate_detection_bounds,
)
from app.services.yolo_detection import (  # noqa: E402
    decode_yolo_output,
    letterbox_image,
)

CONTRACT_VERSION = 1
IOU_THRESHOLD = 0.5
MODEL_SHA256 = "a599289e5c25ab693fd7c6a152093f95fc34aef9b59b2c798127173e6e7ba2d9"
MODEL_SIZE_BYTES = 12_265_233
ONNX_INPUT_SIZE = 640
CONFIDENCE_THRESHOLD = 0.25
NMS_IOU_THRESHOLD = 0.45


class BenchmarkError(RuntimeError):
    """A configuration, fixture, detector, or output failure."""


@dataclass
class DetectionResult:
    """Raw result for one fixture."""

    file: str
    backend: str
    expected_detections: int
    detections: list[PlateDetection]
    latency_ms: float
    best_iou_by_ground_truth: list[float]
    valid: bool
    error: str | None = None


def current_process_rss_mb() -> float | None:
    """Return current process RSS on Windows; otherwise leave it unknown."""

    if sys.platform != "win32":
        return None

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    get_current_process = ctypes.windll.kernel32.GetCurrentProcess
    get_process_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
    get_current_process.restype = ctypes.c_void_p
    get_process_memory_info.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ProcessMemoryCounters),
        ctypes.c_ulong,
    ]
    get_process_memory_info.restype = ctypes.c_int
    if not get_process_memory_info(
        get_current_process(), ctypes.byref(counters), counters.cb
    ):
        return None
    return round(counters.WorkingSetSize / (1024 * 1024), 3)


class OnnxPlateDetector:
    """Day 4 research adapter for the exact selected ONNX artifact."""

    def __init__(self, model_path: Path) -> None:
        if not model_path.is_file():
            raise BenchmarkError(f"ONNX model not found: {model_path}")
        if model_path.stat().st_size != MODEL_SIZE_BYTES:
            raise BenchmarkError("ONNX model size does not match published artifact")
        digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
        if digest != MODEL_SHA256:
            raise BenchmarkError("ONNX model SHA-256 does not match published artifact")

        self.rss_before_load_mb = current_process_rss_mb()
        started = time.perf_counter()
        try:
            self.session = ort.InferenceSession(
                str(model_path), providers=["CPUExecutionProvider"]
            )
        except Exception as exc:
            raise BenchmarkError(f"ONNX Runtime could not load model: {exc}") from exc
        self.load_latency_ms = round((time.perf_counter() - started) * 1000, 3)
        self.rss_after_load_mb = current_process_rss_mb()
        self.max_observed_rss_mb = self.rss_after_load_mb

        inputs = self.session.get_inputs()
        outputs = self.session.get_outputs()
        if len(inputs) != 1 or (
            inputs[0].name,
            inputs[0].shape,
            inputs[0].type,
        ) != ("images", [1, 3, 640, 640], "tensor(float)"):
            raise BenchmarkError("Unexpected ONNX input tensor contract")
        if len(outputs) != 1 or (
            outputs[0].name,
            outputs[0].shape,
            outputs[0].type,
        ) != ("output0", [1, 5, 8400], "tensor(float)"):
            raise BenchmarkError("Unexpected ONNX output tensor contract")

        metadata = self.session.get_modelmeta().custom_metadata_map
        if metadata.get("names") != "{0: 'license_plate'}":
            raise BenchmarkError("Unexpected ONNX class mapping")

    @property
    def metadata(self) -> dict[str, Any]:
        input_node = self.session.get_inputs()[0]
        output_node = self.session.get_outputs()[0]
        model_metadata = self.session.get_modelmeta().custom_metadata_map
        return {
            "artifact_size_bytes": MODEL_SIZE_BYTES,
            "artifact_sha256": MODEL_SHA256,
            "onnxruntime": ort.__version__,
            "providers": self.session.get_providers(),
            "input": {
                "name": input_node.name,
                "shape": input_node.shape,
                "type": input_node.type,
                "layout": "NCHW",
            },
            "outputs": [
                {
                    "name": output_node.name,
                    "shape": output_node.shape,
                    "type": output_node.type,
                    "layout": "[batch, x_center/y_center/width/height/class0, anchors]",
                }
            ],
            "class_mapping": {"0": "license_plate"},
            "export": {
                "ultralytics_version": model_metadata.get("version"),
                "opset": 12,
                "nms_embedded": False,
            },
            "preprocessing": {
                "color": "BGR to RGB",
                "letterbox": "640x640, value 114, stride 32",
                "dtype": "float32",
                "normalization": "divide uint8 values by 255",
            },
            "postprocessing": {
                "confidence_threshold": CONFIDENCE_THRESHOLD,
                "nms_iou_threshold": NMS_IOU_THRESHOLD,
                "raw_box_format": "cxcywh in 640x640 letterboxed pixels",
                "output_box_format": "clipped original-image xyxy",
            },
            "model_load_latency_ms": self.load_latency_ms,
            "rss_before_load_mb": self.rss_before_load_mb,
            "rss_after_load_mb": self.rss_after_load_mb,
            "max_observed_rss_mb": self.max_observed_rss_mb,
            "memory_measurement": (
                "Windows process working set sampled before load, after load, "
                "and after each inference; not a continuous peak measurement"
            ),
        }

    @staticmethod
    def _letterbox(image: np.ndarray) -> tuple[np.ndarray, float, int, int]:
        return letterbox_image(image)

    def detect(self, image_path: Path) -> list[PlateDetection]:
        image = cv2.imread(str(image_path))
        if image is None:
            raise BenchmarkError(f"OpenCV could not decode image: {image_path}")
        image_height, image_width = image.shape[:2]
        tensor, scale, pad_left, pad_top = self._letterbox(image)
        raw_output = self.session.run(["output0"], {"images": tensor})[0]
        observed_rss = current_process_rss_mb()
        if observed_rss is not None:
            self.max_observed_rss_mb = max(
                self.max_observed_rss_mb or observed_rss, observed_rss
            )
        try:
            return decode_yolo_output(
                raw_output,
                image_width,
                image_height,
                scale,
                pad_left,
                pad_top,
                CONFIDENCE_THRESHOLD,
                NMS_IOU_THRESHOLD,
            )
        except ValueError as exc:
            raise BenchmarkError(str(exc)) from exc


def detect_contour(image_path: Path) -> list[PlateDetection]:
    """Return heuristic plate candidates using OpenCV contour operations."""

    image = cv2.imread(str(image_path))
    if image is None:
        raise BenchmarkError(f"OpenCV could not decode image: {image_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 100, 200)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 3))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    image_height, image_width = image.shape[:2]
    detections: list[PlateDetection] = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        aspect_ratio = width / height if height else 0.0
        area_ratio = (width * height) / (image_width * image_height)
        if 2.0 <= aspect_ratio <= 6.0 and 0.005 <= area_ratio <= 0.15:
            heuristic_confidence = max(0.0, 1.0 - abs(aspect_ratio - 4.0) / 3.0)
            detection = PlateDetection(
                bbox=(x, y, x + width, y + height),
                confidence=float(round(heuristic_confidence, 3)),
                label="plate_candidate",
            )
            validate_detection_bounds(detection, image_width, image_height)
            detections.append(detection)

    detections.sort(key=lambda detection: detection.confidence, reverse=True)
    return detections


def iou(
    box_a: tuple[int, int, int, int],
    box_b: tuple[int, int, int, int],
) -> float:
    """Calculate intersection over union for two xyxy boxes."""

    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])

    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = max(0, box_a[2] - box_a[0]) * max(0, box_a[3] - box_a[1])
    area_b = max(0, box_b[2] - box_b[0]) * max(0, box_b[3] - box_b[1])
    union = area_a + area_b - intersection
    return intersection / union if union else 0.0


def _require_int(value: Any, context: str) -> int:
    if type(value) is not int:
        raise BenchmarkError(f"{context} must be an integer")
    return value


def load_ground_truth(input_dir: Path) -> list[dict[str, Any]]:
    """Load and validate the generated-fixture manifest."""

    manifest_path = input_dir / "ground_truth.json"
    if not manifest_path.is_file():
        raise BenchmarkError(f"Ground truth not found: {manifest_path}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"Could not read ground truth: {exc}") from exc

    if not isinstance(data, list) or not data:
        raise BenchmarkError("Ground truth must be a non-empty list")

    required = {
        "file",
        "width",
        "height",
        "expected_detections",
        "bounding_boxes",
        "source",
        "license",
    }
    seen_files: set[str] = set()
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise BenchmarkError(f"Ground truth entry {index} must be an object")
        missing = required - entry.keys()
        if missing:
            raise BenchmarkError(f"Ground truth entry {index} is missing {missing}")

        filename = entry["file"]
        if not isinstance(filename, str) or not filename:
            raise BenchmarkError(f"Ground truth entry {index} has invalid file")
        if filename in seen_files:
            raise BenchmarkError(f"Duplicate fixture filename: {filename}")
        seen_files.add(filename)

        width = _require_int(entry["width"], f"{filename}.width")
        height = _require_int(entry["height"], f"{filename}.height")
        expected = _require_int(
            entry["expected_detections"], f"{filename}.expected_detections"
        )
        if width <= 0 or height <= 0 or expected < 0:
            raise BenchmarkError(f"{filename} has invalid dimensions/count")

        boxes = entry["bounding_boxes"]
        if not isinstance(boxes, list) or len(boxes) != expected:
            raise BenchmarkError(
                f"{filename} expected count must equal bounding-box count"
            )
        for box in boxes:
            if not isinstance(box, dict):
                raise BenchmarkError(f"{filename} has a non-object bbox")
            try:
                detection = PlateDetection(
                    bbox=tuple(
                        _require_int(box[key], f"{filename}.{key}")
                        for key in ("x1", "y1", "x2", "y2")
                    ),
                    confidence=1.0,
                    label="license_plate",
                )
            except KeyError as exc:
                raise BenchmarkError(
                    f"{filename} bbox is missing {exc.args[0]}"
                ) from exc
            validate_detection_bounds(detection, width, height)

        fixture_path = input_dir / filename
        if not fixture_path.is_file():
            raise BenchmarkError(f"Fixture not found: {fixture_path}")

    return data


def run_benchmark(
    input_dir: Path,
    backend: str,
    model_path: Path | None = None,
    runtime_metadata: dict[str, Any] | None = None,
) -> list[DetectionResult]:
    """Run an available Day 4 backend and score every fixture."""

    detector: Any
    if backend == "contour":
        detector = detect_contour
    elif backend == "onnx":
        if model_path is None:
            raise BenchmarkError("ONNX backend requires --model")
        onnx_detector = OnnxPlateDetector(model_path)
        detector = onnx_detector.detect
        if runtime_metadata is not None:
            runtime_metadata.update(onnx_detector.metadata)
    else:
        raise BenchmarkError(
            f"Unknown backend {backend!r}; expected 'contour' or 'onnx'"
        )

    results: list[DetectionResult] = []
    for entry in load_ground_truth(input_dir):
        image_path = input_dir / entry["file"]
        started = time.perf_counter()
        try:
            image = cv2.imread(str(image_path))
            if image is None:
                raise BenchmarkError(f"OpenCV could not decode image: {image_path}")
            actual_height, actual_width = image.shape[:2]
            if (actual_width, actual_height) != (entry["width"], entry["height"]):
                raise BenchmarkError(
                    f"{entry['file']} dimensions do not match ground truth"
                )

            detections = detector(image_path)
            latency_ms = (time.perf_counter() - started) * 1000
            if backend == "onnx" and runtime_metadata is not None:
                runtime_metadata.update(onnx_detector.metadata)
            ground_truth_boxes = [
                (box["x1"], box["y1"], box["x2"], box["y2"])
                for box in entry["bounding_boxes"]
            ]
            best_ious = [
                max((iou(gt_box, det.bbox) for det in detections), default=0.0)
                for gt_box in ground_truth_boxes
            ]
            valid = len(detections) == entry["expected_detections"] and all(
                score >= IOU_THRESHOLD for score in best_ious
            )
            result = DetectionResult(
                file=entry["file"],
                backend=backend,
                expected_detections=entry["expected_detections"],
                detections=detections,
                latency_ms=round(latency_ms, 3),
                best_iou_by_ground_truth=[round(score, 6) for score in best_ious],
                valid=valid,
            )
        except Exception as exc:
            result = DetectionResult(
                file=entry["file"],
                backend=backend,
                expected_detections=entry["expected_detections"],
                detections=[],
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                best_iou_by_ground_truth=[],
                valid=False,
                error=f"{type(exc).__name__}: {exc}",
            )
        results.append(result)

        marker = "PASS" if result.valid else "FAIL"
        print(
            f"[{marker}] {result.file}: expected={result.expected_detections} "
            f"actual={len(result.detections)} latency={result.latency_ms:.3f}ms"
        )
        if result.best_iou_by_ground_truth:
            print(f"       best IoU by ground truth: {result.best_iou_by_ground_truth}")
        if result.error:
            print(f"       error: {result.error}")

    return results


def write_results(
    output_path: Path,
    input_dir: Path,
    backend: str,
    results: list[DetectionResult],
    runtime_metadata: dict[str, Any] | None = None,
) -> None:
    """Write retained raw results and environment metadata."""

    latencies = [result.latency_ms for result in results]
    payload = {
        "schema_version": 1,
        "measurement_class": "locally measured",
        "command_backend": backend,
        "input": input_dir.as_posix(),
        "contract_version": CONTRACT_VERSION,
        "iou_threshold": IOU_THRESHOLD,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "opencv": cv2.__version__,
            "onnxruntime": ort.__version__,
        },
        "runtime": runtime_metadata or {},
        "summary": {
            "fixtures": len(results),
            "valid_fixtures": sum(result.valid for result in results),
            "invalid_fixtures": sum(not result.valid for result in results),
            "errors": sum(result.error is not None for result in results),
            "total_detections": sum(len(result.detections) for result in results),
            "average_latency_ms": (
                round(sum(latencies) / len(latencies), 3) if latencies else None
            ),
        },
        "results": [
            {
                **asdict(result),
                "detections": [asdict(detection) for detection in result.detections],
            }
            for result in results
        ],
    }
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise BenchmarkError(f"Could not write results: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark a Day 4 plate-detector candidate against generated "
            "fixtures. This research harness is not the Day 5 API integration."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("sample-data/evaluation"),
        help="Fixture directory containing ground_truth.json",
    )
    parser.add_argument(
        "--backend",
        choices=("contour", "onnx"),
        default="contour",
        help="Day 4 backend to benchmark (default: contour)",
    )
    parser.add_argument(
        "--model",
        type=Path,
        help="Ignored local best.onnx path; required by --backend onnx",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON path for retained raw results",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime_metadata: dict[str, Any] = {}
    try:
        results = run_benchmark(
            args.input,
            args.backend,
            model_path=args.model,
            runtime_metadata=runtime_metadata,
        )
        if args.output:
            write_results(
                args.output,
                args.input,
                args.backend,
                results,
                runtime_metadata=runtime_metadata,
            )
            print(f"Raw results: {args.output}")
    except BenchmarkError as exc:
        print(f"benchmark error: {exc}", file=sys.stderr)
        return 2

    valid_count = sum(result.valid for result in results)
    print(f"Valid fixtures: {valid_count}/{len(results)}")
    if any(not result.valid for result in results):
        print("benchmark result is invalid", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
