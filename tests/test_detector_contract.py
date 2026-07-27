"""Day 4 detector contract, fixture, and benchmark-honesty tests."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import cv2
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from benchmark_detector import (  # noqa: E402
    BenchmarkError,
    DetectionResult,
    MODEL_SHA256,
    MODEL_SIZE_BYTES,
    OnnxPlateDetector,
    PlateDetection,
    detect_contour,
    iou,
    load_ground_truth,
    main,
    run_benchmark,
    validate_detection_bounds,
    write_results,
)

EVALUATION_DIR = Path(__file__).resolve().parent.parent / "sample-data" / "evaluation"
MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "day4" / "best.onnx"


class TestPlateDetectionContract:
    def test_required_fields(self) -> None:
        detection = PlateDetection(
            bbox=(10, 20, 110, 70),
            confidence=0.85,
            label="license_plate",
        )
        assert detection.bbox == (10, 20, 110, 70)
        assert detection.confidence == 0.85
        assert detection.label == "license_plate"

    def test_missing_required_field_is_rejected(self) -> None:
        with pytest.raises(TypeError):
            PlateDetection(  # type: ignore[call-arg]
                bbox=(10, 20, 110, 70),
                confidence=0.85,
            )

    def test_contract_is_immutable(self) -> None:
        detection = PlateDetection((0, 0, 10, 10), 0.5, "license_plate")
        with pytest.raises(FrozenInstanceError):
            detection.confidence = 0.7  # type: ignore[misc]

    @pytest.mark.parametrize(
        "bbox",
        [
            [0, 0, 10, 10],
            (0, 0, 10),
            (0, 0, 10, 10, 20),
            (0.0, 0, 10, 10),
            (False, 0, 10, 10),
            ("0", 0, 10, 10),
        ],
    )
    def test_rejects_invalid_bbox_type(self, bbox: object) -> None:
        with pytest.raises(TypeError):
            PlateDetection(bbox, 0.5, "license_plate")  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "bbox",
        [
            (-1, 0, 10, 10),
            (0, -1, 10, 10),
            (10, 0, 10, 10),
            (11, 0, 10, 10),
            (0, 10, 10, 10),
            (0, 11, 10, 10),
        ],
    )
    def test_rejects_invalid_bbox_coordinates(
        self, bbox: tuple[int, int, int, int]
    ) -> None:
        with pytest.raises(ValueError):
            PlateDetection(bbox, 0.5, "license_plate")

    @pytest.mark.parametrize("confidence", [0, 1, "0.5", None, True])
    def test_rejects_non_float_confidence(self, confidence: object) -> None:
        with pytest.raises(TypeError):
            PlateDetection(
                (0, 0, 10, 10),
                confidence,  # type: ignore[arg-type]
                "license_plate",
            )

    @pytest.mark.parametrize(
        "confidence", [-0.001, 1.001, math.nan, math.inf, -math.inf]
    )
    def test_rejects_invalid_float_confidence(self, confidence: float) -> None:
        with pytest.raises(ValueError):
            PlateDetection((0, 0, 10, 10), confidence, "license_plate")

    @pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
    def test_accepts_confidence_boundaries(self, confidence: float) -> None:
        assert (
            PlateDetection((0, 0, 10, 10), confidence, "license_plate").confidence
            == confidence
        )

    @pytest.mark.parametrize("label", ["", "   "])
    def test_rejects_empty_label(self, label: str) -> None:
        with pytest.raises(ValueError):
            PlateDetection((0, 0, 10, 10), 0.5, label)

    def test_rejects_non_string_label(self) -> None:
        with pytest.raises(TypeError):
            PlateDetection((0, 0, 10, 10), 0.5, None)  # type: ignore[arg-type]

    def test_validates_image_bounds(self) -> None:
        detection = PlateDetection((0, 0, 101, 50), 0.5, "license_plate")
        with pytest.raises(ValueError, match="clipped"):
            validate_detection_bounds(detection, 100, 50)

    @pytest.mark.parametrize("dimensions", [(0, 10), (10, 0), (-1, 10)])
    def test_rejects_invalid_image_dimensions(
        self, dimensions: tuple[int, int]
    ) -> None:
        detection = PlateDetection((0, 0, 1, 1), 0.5, "license_plate")
        with pytest.raises(ValueError):
            validate_detection_bounds(detection, *dimensions)


class TestDetectionResultContract:
    def test_required_fields(self) -> None:
        result = DetectionResult(
            file="fixture.png",
            backend="contour",
            expected_detections=0,
            detections=[],
            latency_ms=1.0,
            best_iou_by_ground_truth=[],
            valid=True,
        )
        assert result.error is None
        assert result.valid is True


class TestIoU:
    def test_identical_boxes(self) -> None:
        assert iou((10, 10, 50, 50), (10, 10, 50, 50)) == pytest.approx(1.0)

    def test_disjoint_boxes(self) -> None:
        assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0

    def test_partial_overlap(self) -> None:
        assert iou((0, 0, 10, 10), (5, 5, 15, 15)) == pytest.approx(25 / 175)

    def test_zero_area_is_safe(self) -> None:
        assert iou((0, 0, 0, 0), (0, 0, 10, 10)) == 0.0


class TestFixtureIntegrity:
    @pytest.fixture()
    def ground_truth(self) -> list[dict]:
        return load_ground_truth(EVALUATION_DIR)

    def test_fixture_set_has_plate_no_plate_and_multiple(
        self, ground_truth: list[dict]
    ) -> None:
        counts = [entry["expected_detections"] for entry in ground_truth]
        assert len(ground_truth) == 4
        assert 0 in counts
        assert any(count > 1 for count in counts)

    def test_each_fixture_decodes_at_declared_dimensions(
        self, ground_truth: list[dict]
    ) -> None:
        for entry in ground_truth:
            image = cv2.imread(str(EVALUATION_DIR / entry["file"]))
            assert image is not None
            height, width = image.shape[:2]
            assert (width, height) == (entry["width"], entry["height"])

    def test_each_bbox_is_within_declared_dimensions(
        self, ground_truth: list[dict]
    ) -> None:
        for entry in ground_truth:
            assert entry["expected_detections"] == len(entry["bounding_boxes"])
            for box in entry["bounding_boxes"]:
                detection = PlateDetection(
                    bbox=(box["x1"], box["y1"], box["x2"], box["y2"]),
                    confidence=1.0,
                    label="license_plate",
                )
                validate_detection_bounds(detection, entry["width"], entry["height"])

    def test_provenance_is_explicit(self, ground_truth: list[dict]) -> None:
        for entry in ground_truth:
            assert entry["source"].startswith("project-generated")
            assert "README.md" in entry["license"]

    def test_manifest_rejects_missing_fixture(self, tmp_path: Path) -> None:
        manifest = [
            {
                "file": "missing.png",
                "width": 10,
                "height": 10,
                "expected_detections": 0,
                "bounding_boxes": [],
                "source": "project-generated",
                "license": "see README.md",
            }
        ]
        (tmp_path / "ground_truth.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        with pytest.raises(BenchmarkError, match="Fixture not found"):
            load_ground_truth(tmp_path)


class TestContourBenchmark:
    def test_returns_contract_compliant_sorted_results(self) -> None:
        detections = detect_contour(EVALUATION_DIR / "synthetic_multi_plate.png")
        assert all(isinstance(item, PlateDetection) for item in detections)
        assert all(item.label == "plate_candidate" for item in detections)
        confidences = [item.confidence for item in detections]
        assert confidences == sorted(confidences, reverse=True)

    def test_missing_image_is_an_error(self) -> None:
        with pytest.raises(BenchmarkError, match="could not decode"):
            detect_contour(Path("missing-fixture.png"))

    def test_onnx_backend_requires_explicit_model(self) -> None:
        with pytest.raises(BenchmarkError, match="requires --model"):
            run_benchmark(EVALUATION_DIR, "onnx")

    def test_invalid_results_return_nonzero_and_are_retained(
        self, tmp_path: Path
    ) -> None:
        output = tmp_path / "raw.json"
        exit_code = main(
            [
                "--input",
                str(EVALUATION_DIR),
                "--backend",
                "contour",
                "--output",
                str(output),
            ]
        )
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert exit_code == 1
        assert payload["measurement_class"] == "locally measured"
        assert payload["summary"]["invalid_fixtures"] > 0

    def test_raw_result_contains_environment_and_detections(
        self, tmp_path: Path
    ) -> None:
        results = run_benchmark(EVALUATION_DIR, "contour")
        output = tmp_path / "raw.json"
        write_results(output, EVALUATION_DIR, "contour", results)
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["environment"]["python"]
        assert payload["environment"]["opencv"] == cv2.__version__
        assert len(payload["results"]) == 4


class TestExactOnnxResearchAdapter:
    def test_letterbox_produces_declared_input_contract(self) -> None:
        image = cv2.imread(str(EVALUATION_DIR / "synthetic_plate_white.png"))
        assert image is not None
        tensor, scale, pad_left, pad_top = OnnxPlateDetector._letterbox(image)
        assert tensor.shape == (1, 3, 640, 640)
        assert tensor.dtype.name == "float32"
        assert 0.0 <= float(tensor.min()) <= float(tensor.max()) <= 1.0
        assert scale == 1.0
        assert (pad_left, pad_top) == (0, 80)

    def test_exact_artifact_loads_and_matches_contract(self) -> None:
        if not MODEL_PATH.is_file():
            pytest.skip("immutable ONNX artifact is not present in ignored models/day4")
        assert MODEL_PATH.stat().st_size == MODEL_SIZE_BYTES
        assert hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest() == MODEL_SHA256
        detector = OnnxPlateDetector(MODEL_PATH)
        detections = detector.detect(EVALUATION_DIR / "synthetic_plate_white.png")
        assert detections
        assert all(item.label == "license_plate" for item in detections)
        assert all(isinstance(item, PlateDetection) for item in detections)

    def test_exact_artifact_validates_all_generated_fixtures(self) -> None:
        if not MODEL_PATH.is_file():
            pytest.skip("immutable ONNX artifact is not present in ignored models/day4")
        metadata: dict = {}
        results = run_benchmark(
            EVALUATION_DIR,
            "onnx",
            model_path=MODEL_PATH,
            runtime_metadata=metadata,
        )
        assert all(result.valid for result in results)
        assert metadata["input"]["shape"] == [1, 3, 640, 640]
        assert metadata["outputs"][0]["shape"] == [1, 5, 8400]
        assert metadata["class_mapping"] == {"0": "license_plate"}
