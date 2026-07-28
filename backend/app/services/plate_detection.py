"""Lazy ONNX Runtime CPU service for still-image plate detection."""

from __future__ import annotations

import base64
import hashlib
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np
import onnxruntime as ort

from app.core.config import Settings
from app.schemas.detection import (
    BoundingBox,
    ImageDetectionResponse,
    PlateCropResponse,
    PlateDetectionResponse,
)
from app.services.detection_contract import (
    PlateDetection,
)
from app.services.yolo_detection import decode_yolo_output, letterbox_image

MODEL_SHA256 = "a599289e5c25ab693fd7c6a152093f95fc34aef9b59b2c798127173e6e7ba2d9"
MODEL_SIZE_BYTES = 12_265_233


class PlateDetectionError(RuntimeError):
    """Expected detector configuration/runtime failure with a stable code."""

    def __init__(self, code: str, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class DetectedPlate:
    """Validated localization paired with a copied original-image crop."""

    detection: PlateDetection
    crop: np.ndarray


class DetectionDebugSink(Protocol):
    """Optional isolated observer; the production service writes no debug files."""

    def __call__(
        self, correlation_id: str, image: np.ndarray, plates: list[DetectedPlate]
    ) -> None: ...


class OnnxPlateDetector:
    """Exact Day 4 selected model, loaded with ONNX Runtime CPU only."""

    def __init__(
        self, model_path: Path, confidence_threshold: float, nms_iou_threshold: float
    ) -> None:
        if not model_path.is_file():
            raise PlateDetectionError(
                "DETECTOR_MODEL_MISSING",
                "The plate detection model is not available.",
            )
        try:
            size = model_path.stat().st_size
            digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
        except OSError as exc:
            raise PlateDetectionError(
                "DETECTOR_MODEL_UNREADABLE",
                "The plate detection model cannot be read.",
            ) from exc
        if size != MODEL_SIZE_BYTES or digest != MODEL_SHA256:
            raise PlateDetectionError(
                "DETECTOR_MODEL_INVALID",
                "The plate detection model failed artifact validation.",
            )

        try:
            session = ort.InferenceSession(
                str(model_path), providers=["CPUExecutionProvider"]
            )
        except Exception as exc:
            raise PlateDetectionError(
                "DETECTOR_MODEL_UNLOADABLE",
                "The plate detection model could not be loaded.",
            ) from exc

        if session.get_providers() != ["CPUExecutionProvider"]:
            raise PlateDetectionError(
                "DETECTOR_PROVIDER_INVALID",
                "The detector must use the CPU execution provider.",
            )
        inputs = session.get_inputs()
        outputs = session.get_outputs()
        if len(inputs) != 1 or (
            inputs[0].name,
            inputs[0].shape,
            inputs[0].type,
        ) != ("images", [1, 3, 640, 640], "tensor(float)"):
            raise PlateDetectionError(
                "DETECTOR_MODEL_CONTRACT_INVALID",
                "The plate detection model has an unsupported input contract.",
            )
        if len(outputs) != 1 or (
            outputs[0].name,
            outputs[0].shape,
            outputs[0].type,
        ) != ("output0", [1, 5, 8400], "tensor(float)"):
            raise PlateDetectionError(
                "DETECTOR_MODEL_CONTRACT_INVALID",
                "The plate detection model has an unsupported output contract.",
            )
        if session.get_modelmeta().custom_metadata_map.get("names") != (
            "{0: 'license_plate'}"
        ):
            raise PlateDetectionError(
                "DETECTOR_MODEL_CONTRACT_INVALID",
                "The plate detection model has an unsupported class mapping.",
            )

        self._session = session
        self._confidence_threshold = confidence_threshold
        self._nms_iou_threshold = nms_iou_threshold

    @staticmethod
    def _letterbox(image: np.ndarray) -> tuple[np.ndarray, float, int, int]:
        return letterbox_image(image)

    def detect(self, image: np.ndarray) -> tuple[list[PlateDetection], float]:
        """Infer and map sorted detections into original-image coordinates."""

        image_height, image_width = image.shape[:2]
        tensor, scale, pad_left, pad_top = self._letterbox(image)
        started = time.perf_counter()
        try:
            raw_output = self._session.run(["output0"], {"images": tensor})[0]
        except Exception as exc:
            raise PlateDetectionError(
                "DETECTOR_INFERENCE_FAILED",
                "Plate detection could not be completed.",
            ) from exc
        inference_ms = round((time.perf_counter() - started) * 1000, 3)
        try:
            detections = decode_yolo_output(
                raw_output,
                image_width,
                image_height,
                scale,
                pad_left,
                pad_top,
                self._confidence_threshold,
                self._nms_iou_threshold,
            )
        except ValueError as exc:
            raise PlateDetectionError(
                "DETECTOR_OUTPUT_INVALID",
                "The plate detector returned an unsupported result.",
            ) from exc
        return detections, inference_ms


class PlateDetectionService:
    """Own one lazily initialized detector for repeated application requests."""

    def __init__(
        self, settings: Settings, debug_sink: DetectionDebugSink | None = None
    ) -> None:
        self._settings = settings
        self._debug_sink = debug_sink
        self._detector: OnnxPlateDetector | None = None
        self._load_lock = threading.Lock()

    def _get_detector(self) -> OnnxPlateDetector:
        if self._detector is None:
            with self._load_lock:
                if self._detector is None:
                    model_path = self._settings.detector_model_path
                    if model_path is None:
                        raise PlateDetectionError(
                            "DETECTOR_MODEL_NOT_CONFIGURED",
                            "The plate detection model path is not configured.",
                        )
                    self._detector = OnnxPlateDetector(
                        model_path,
                        self._settings.detector_confidence_threshold,
                        self._settings.detector_nms_iou_threshold,
                    )
        return self._detector

    def detect(self, image_bytes: bytes, correlation_id: str) -> ImageDetectionResponse:
        """Decode validated bytes, detect plates, and return lossless crops."""

        started = time.perf_counter()
        encoded = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            raise PlateDetectionError(
                "DETECTOR_IMAGE_DECODE_FAILED",
                "The validated image could not be prepared for detection.",
                422,
            )

        detections, inference_ms = self._get_detector().detect(image)
        detected_plates = self._extract_crops(image, detections)
        if self._debug_sink is not None:
            self._debug_sink(correlation_id, image, detected_plates)
        responses = [self._serialize_plate(item) for item in detected_plates]
        total_ms = round((time.perf_counter() - started) * 1000, 3)
        return ImageDetectionResponse(
            correlation_id=correlation_id,
            status="no_plate_detected" if not responses else "detected",
            detection_count=len(responses),
            image_width=int(image.shape[1]),
            image_height=int(image.shape[0]),
            inference_ms=inference_ms,
            total_ms=total_ms,
            detections=responses,
        )

    @staticmethod
    def _extract_crops(
        image: np.ndarray, detections: list[PlateDetection]
    ) -> list[DetectedPlate]:
        crops: list[DetectedPlate] = []
        for detection in detections:
            x1, y1, x2, y2 = detection.bbox
            crop = image[y1:y2, x1:x2].copy()
            if crop.size == 0:
                raise PlateDetectionError(
                    "DETECTOR_CROP_FAILED",
                    "A detected plate could not be cropped safely.",
                )
            crops.append(DetectedPlate(detection=detection, crop=crop))
        return crops

    @staticmethod
    def _serialize_plate(plate: DetectedPlate) -> PlateDetectionResponse:
        success, png = cv2.imencode(".png", plate.crop)
        if not success:
            raise PlateDetectionError(
                "DETECTOR_CROP_ENCODING_FAILED",
                "A detected plate crop could not be encoded.",
            )
        x1, y1, x2, y2 = plate.detection.bbox
        return PlateDetectionResponse(
            bbox=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
            confidence=plate.detection.confidence,
            label=plate.detection.label,
            crop=PlateCropResponse(
                media_type="image/png",
                base64_data=base64.b64encode(png.tobytes()).decode("ascii"),
                width=x2 - x1,
                height=y2 - y1,
            ),
        )
