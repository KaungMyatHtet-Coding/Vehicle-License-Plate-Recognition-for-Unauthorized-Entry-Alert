"""Shared preprocessing and decoding for the selected YOLO ONNX contract."""

from __future__ import annotations

import math

import cv2
import numpy as np

from app.services.detection_contract import (
    PlateDetection,
    validate_detection_bounds,
)

ONNX_INPUT_SIZE = 640


def letterbox_image(image: np.ndarray) -> tuple[np.ndarray, float, int, int]:
    """Create the verified float32 NCHW model tensor without distorting aspect."""

    image_height, image_width = image.shape[:2]
    scale = min(ONNX_INPUT_SIZE / image_width, ONNX_INPUT_SIZE / image_height)
    resized_width = round(image_width * scale)
    resized_height = round(image_height * scale)
    resized = cv2.resize(
        image, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR
    )
    pad_width = (ONNX_INPUT_SIZE - resized_width) / 2
    pad_height = (ONNX_INPUT_SIZE - resized_height) / 2
    left = round(pad_width - 0.1)
    right = round(pad_width + 0.1)
    top = round(pad_height - 0.1)
    bottom = round(pad_height + 0.1)
    padded = cv2.copyMakeBorder(
        resized,
        top,
        bottom,
        left,
        right,
        cv2.BORDER_CONSTANT,
        value=(114, 114, 114),
    )
    rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
    tensor = np.ascontiguousarray(rgb.transpose(2, 0, 1)[None], dtype=np.float32)
    tensor /= 255.0
    return tensor, scale, left, top


def decode_yolo_output(
    raw_output: np.ndarray,
    image_width: int,
    image_height: int,
    scale: float,
    pad_left: int,
    pad_top: int,
    confidence_threshold: float,
    nms_iou_threshold: float,
) -> list[PlateDetection]:
    """Map verified YOLO output to confidence-sorted original-pixel boxes."""

    if raw_output.shape != (1, 5, 8400):
        raise ValueError(f"Unexpected runtime output shape: {raw_output.shape}")

    predictions = raw_output[0].T
    indices = np.flatnonzero(predictions[:, 4] >= confidence_threshold)
    boxes: list[list[float]] = []
    scores: list[float] = []
    for index in indices:
        center_x, center_y, width, height = predictions[index, :4]
        boxes.append(
            [
                float(center_x - width / 2),
                float(center_y - height / 2),
                float(width),
                float(height),
            ]
        )
        scores.append(float(predictions[index, 4]))

    kept = cv2.dnn.NMSBoxes(
        boxes,
        scores,
        confidence_threshold,
        nms_iou_threshold,
    )
    detections: list[PlateDetection] = []
    for raw_index in np.asarray(kept).reshape(-1):
        index = int(raw_index)
        box_x, box_y, box_width, box_height = boxes[index]
        x1 = max(0, math.floor((box_x - pad_left) / scale))
        y1 = max(0, math.floor((box_y - pad_top) / scale))
        x2 = min(image_width, math.ceil((box_x + box_width - pad_left) / scale))
        y2 = min(image_height, math.ceil((box_y + box_height - pad_top) / scale))
        if x2 <= x1 or y2 <= y1:
            continue
        detection = PlateDetection(
            bbox=(x1, y1, x2, y2),
            confidence=float(scores[index]),
            label="license_plate",
        )
        validate_detection_bounds(detection, image_width, image_height)
        detections.append(detection)

    detections.sort(key=lambda item: item.confidence, reverse=True)
    return detections
