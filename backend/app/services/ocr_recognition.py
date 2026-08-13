"""Lazy local RapidOCR service with separate conservative normalization."""

from __future__ import annotations

import importlib.metadata
import math
import threading
import time
from dataclasses import dataclass
from typing import Literal, Protocol

import cv2
import numpy as np

from app.core.config import Settings
from app.schemas.ocr import PlateOcrResponse
from app.services.plate_preprocessing import (
    PlatePreprocessingError,
    PlatePreprocessingService,
    PreprocessingOptions,
)

ALLOWED_PLATE_CHARACTERS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
OcrMode = Literal["recognition_only", "full_pipeline"]


def is_plate_grammar_reliable(
    normalized_text: str,
    supported_regions: list[str],
    minimum_length: int,
    maximum_length: int,
) -> bool:
    """Accept only conservative, configurable region-plus-number structures."""

    if not isinstance(normalized_text, str):
        return False
    if not minimum_length <= len(normalized_text) <= maximum_length:
        return False
    if not any(normalized_text.startswith(region) for region in supported_regions):
        return False
    return bool(
        normalized_text.isalnum() and any(char.isdigit() for char in normalized_text)
    )


def plate_review_reason(
    normalized_text: str,
    confidence: float | None,
    supported_regions: list[str],
    minimum_length: int,
    maximum_length: int,
    minimum_confidence: float = 0.80,
) -> str | None:
    """Return a truthful review reason without treating grammar as confidence."""

    if not normalized_text:
        return "OCR_EMPTY"
    if confidence is None or confidence < minimum_confidence:
        return "OCR_LOW_CONFIDENCE"
    if not any(normalized_text.startswith(region) for region in supported_regions):
        if any(character.isdigit() for character in normalized_text):
            return "PLATE_REGION_MISSING"
        return "PLATE_TEXT_UNRELIABLE"
    if not minimum_length <= len(normalized_text) <= maximum_length:
        return "PLATE_FORMAT_UNSUPPORTED"
    if not normalized_text.isalnum() or not any(
        character.isdigit() for character in normalized_text
    ):
        return "PLATE_TEXT_UNRELIABLE"
    return None


class PlateOcrError(RuntimeError):
    """Safe OCR configuration/runtime failure with a stable code."""

    def __init__(self, code: str, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class EngineOcrResult:
    """Unnormalized engine output for one OCR mode."""

    raw_text: str
    confidence: float | None
    inference_ms: float
    mode: OcrMode


class OcrEngine(Protocol):
    """Narrow engine boundary for deterministic service tests."""

    def recognize(self, image: np.ndarray, mode: OcrMode) -> EngineOcrResult: ...


def normalize_plate_text(raw_text: str) -> str:
    """Uppercase and remove whitespace, separators, and unsupported characters."""

    if not isinstance(raw_text, str):
        raise TypeError("raw_text must be a string")
    return "".join(
        character
        for character in raw_text.upper()
        if character in ALLOWED_PLATE_CHARACTERS
    )


class RapidOcrCpuEngine:
    """RapidOCR primary/fallback adapter restricted to ONNX Runtime CPU."""

    def __init__(self) -> None:
        try:
            from rapidocr import RapidOCR

            if importlib.metadata.version("rapidocr") != "3.9.2":
                raise PlateOcrError(
                    "OCR_VERSION_INVALID",
                    "The configured OCR runtime version is unsupported.",
                )
            engine = RapidOCR()
            providers = {
                tuple(component.session.session.get_providers())
                for component in (
                    engine.text_det,
                    engine.text_cls,
                    engine.text_rec,
                )
            }
            if providers != {("CPUExecutionProvider",)}:
                raise PlateOcrError(
                    "OCR_PROVIDER_INVALID",
                    "The OCR runtime must use the CPU execution provider.",
                )
        except PlateOcrError:
            raise
        except (ImportError, importlib.metadata.PackageNotFoundError) as exc:
            raise PlateOcrError(
                "OCR_RUNTIME_MISSING",
                "The local OCR runtime is not available.",
            ) from exc
        except Exception as exc:
            raise PlateOcrError(
                "OCR_RUNTIME_UNLOADABLE",
                "The local OCR runtime could not be initialized.",
            ) from exc
        self._engine = engine

    def recognize(self, image: np.ndarray, mode: OcrMode) -> EngineOcrResult:
        """Run the selected Day 7 mode and retain raw confidence/timing."""

        started = time.perf_counter()
        try:
            if mode == "recognition_only":
                output = self._engine(image, use_det=False, use_cls=False, use_rec=True)
            elif mode == "full_pipeline":
                output = self._engine(image, use_det=True, use_cls=True, use_rec=True)
            else:  # pragma: no cover - Literal plus service-owned calls
                raise PlateOcrError(
                    "OCR_MODE_INVALID", "The requested OCR mode is unsupported."
                )
        except PlateOcrError:
            raise
        except Exception as exc:
            raise PlateOcrError(
                "OCR_INFERENCE_FAILED",
                "Plate text recognition could not be completed.",
            ) from exc

        texts = tuple(getattr(output, "txts", ()) or ())
        scores = tuple(getattr(output, "scores", ()) or ())
        raw_text = "\n".join(
            str(value).strip() for value in texts if str(value).strip()
        )
        confidence = round(float(sum(scores) / len(scores)), 6) if scores else None
        inference_ms = round((time.perf_counter() - started) * 1000, 3)
        return EngineOcrResult(raw_text, confidence, inference_ms, mode)


class PlateOcrService:
    """Reuse one lazy CPU OCR engine and return review-safe normalized text."""

    def __init__(
        self,
        settings: Settings,
        preprocessing_service: PlatePreprocessingService | None = None,
    ) -> None:
        self._settings = settings
        self._preprocessing_service = (
            preprocessing_service or PlatePreprocessingService()
        )
        self._engine: OcrEngine | None = None
        self._load_lock = threading.Lock()

    def _get_engine(self) -> OcrEngine:
        if self._engine is None:
            with self._load_lock:
                if self._engine is None:
                    self._engine = RapidOcrCpuEngine()
        return self._engine

    def recognize(self, image_bytes: bytes, correlation_id: str) -> PlateOcrResponse:
        """Decode a validated crop, recognize it, normalize it, and gate review."""

        started = time.perf_counter()
        image = cv2.imdecode(
            np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR
        )
        if image is None:
            raise PlateOcrError(
                "OCR_IMAGE_DECODE_FAILED",
                "The validated plate image could not be prepared for OCR.",
                422,
            )
        original = image.copy()
        try:
            prepared = self._preprocessing_service.preprocess(
                image, PreprocessingOptions()
            ).original
        except PlatePreprocessingError as exc:
            raise PlateOcrError(
                "OCR_PREPROCESSING_FAILED",
                "The plate image could not be prepared for OCR.",
            ) from exc
        if not np.array_equal(image, original):
            raise PlateOcrError(
                "OCR_PREPROCESSING_MUTATED_INPUT",
                "The plate image could not be prepared safely.",
            )

        engine = self._get_engine()
        selected = engine.recognize(prepared, "recognition_only")
        self._validate_result(selected, "recognition_only")
        if self._settings.ocr_full_pipeline_fallback and not self._is_reliable(
            selected
        ):
            fallback = engine.recognize(prepared, "full_pipeline")
            self._validate_result(fallback, "full_pipeline")
            if self._prefer_fallback(selected, fallback):
                selected = fallback

        normalized = self._reconstruct_region_body(selected.raw_text)
        if not normalized:
            review_reason = "OCR_EMPTY"
        elif not self._is_reliable(selected):
            review_reason = "OCR_LOW_CONFIDENCE"
        else:
            review_reason = None
        status = "manual_review" if review_reason is not None else "recognized"

        total_ms = round((time.perf_counter() - started) * 1000, 3)
        return PlateOcrResponse(
            correlation_id=correlation_id,
            status=status,
            review_reason=review_reason,
            raw_text=selected.raw_text,
            normalized_text=normalized,
            confidence=selected.confidence,
            mode=selected.mode,
            inference_ms=selected.inference_ms,
            total_ms=total_ms,
            image_width=int(image.shape[1]),
            image_height=int(image.shape[0]),
        )

    def _reconstruct_region_body(self, raw_text: str) -> str:
        """Normalize ordered OCR lines and join a region with its same-crop body."""

        lines = [normalize_plate_text(line) for line in raw_text.splitlines()]
        lines = [line for line in lines if line]
        if len(lines) > 1:
            supported = tuple(self._settings.supported_plate_regions)
            region = next((line for line in lines if line in supported), None)
            body = next(
                (
                    line
                    for line in lines
                    if line != region and any(c.isdigit() for c in line)
                ),
                None,
            )
            if region and body:
                return region + body
        return normalize_plate_text(raw_text)

    def _is_reliable(self, result: EngineOcrResult) -> bool:
        return (
            bool(normalize_plate_text(result.raw_text))
            and result.confidence is not None
            and result.confidence >= self._settings.ocr_min_confidence
        )

    @staticmethod
    def _validate_result(result: EngineOcrResult, expected_mode: OcrMode) -> None:
        if (
            not isinstance(result, EngineOcrResult)
            or not isinstance(result.raw_text, str)
            or (
                result.confidence is not None
                and (
                    type(result.confidence) is not float
                    or not math.isfinite(result.confidence)
                    or not 0.0 <= result.confidence <= 1.0
                )
            )
            or type(result.inference_ms) is not float
            or not math.isfinite(result.inference_ms)
            or result.inference_ms < 0.0
            or result.mode != expected_mode
        ):
            raise PlateOcrError(
                "OCR_OUTPUT_INVALID",
                "The OCR runtime returned an unsupported result.",
            )

    @staticmethod
    def _prefer_fallback(primary: EngineOcrResult, fallback: EngineOcrResult) -> bool:
        primary_text = normalize_plate_text(primary.raw_text)
        fallback_text = normalize_plate_text(fallback.raw_text)
        if not fallback_text:
            return False
        if not primary_text:
            return True
        return (fallback.confidence or -1.0) > (primary.confidence or -1.0)
