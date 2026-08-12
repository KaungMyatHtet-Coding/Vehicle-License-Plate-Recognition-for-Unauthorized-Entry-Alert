"""Deterministic Phase 4 candidate ranking and persistence-boundary tests."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from app.core.config import Settings
from app.schemas.decision import EntryDecision
from app.schemas.detection import (
    BoundingBox,
    ImageDetectionResponse,
    PlateCropResponse,
    PlateDetectionResponse,
)
from app.schemas.logging import (
    DecisionAuditSnapshot,
    DetectionLoggingResult,
)
from app.schemas.ocr import PlateOcrResponse
from app.services.ocr_recognition import normalize_plate_text
from app.services.recognition_orchestration import RecognitionOrchestrationService

CORRELATION_ID = "11111111-1111-4111-8111-111111111111"
NOW = datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc)


def candidate(
    payload: str,
    *,
    confidence: float,
    bbox: tuple[int, int, int, int],
) -> PlateDetectionResponse:
    return PlateDetectionResponse(
        bbox=BoundingBox(x1=bbox[0], y1=bbox[1], x2=bbox[2], y2=bbox[3]),
        confidence=confidence,
        label="license_plate",
        crop=PlateCropResponse(
            media_type="image/png",
            base64_data=base64.b64encode(payload.encode()).decode(),
            width=bbox[2] - bbox[0],
            height=bbox[3] - bbox[1],
        ),
    )


def detection(candidates: list[PlateDetectionResponse]) -> ImageDetectionResponse:
    return ImageDetectionResponse(
        correlation_id=CORRELATION_ID,
        status="detected" if candidates else "no_plate_detected",
        detection_count=len(candidates),
        image_width=1000,
        image_height=600,
        inference_ms=2.0,
        total_ms=2.0,
        detections=candidates,
    )


class FakeDetector:
    def __init__(self, result: ImageDetectionResponse) -> None:
        self.result = result

    def detect(self, _: bytes, correlation_id: str) -> ImageDetectionResponse:
        return self.result.model_copy(update={"correlation_id": correlation_id})


class FakeOcr:
    def __init__(self, values: dict[str, tuple[str, float]]) -> None:
        self.values = values
        self.calls: list[str] = []

    def recognize(self, crop_bytes: bytes, correlation_id: str) -> PlateOcrResponse:
        key = crop_bytes.decode()
        self.calls.append(key)
        raw_text, confidence = self.values[key]
        return PlateOcrResponse(
            correlation_id=correlation_id,
            status="recognized",
            review_reason=None,
            raw_text=raw_text,
            normalized_text=normalize_plate_text(raw_text),
            confidence=confidence,
            mode="recognition_only",
            inference_ms=3.0,
            total_ms=3.0,
            image_width=60,
            image_height=20,
        )


class FakeDecision:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def decide(self, ocr: PlateOcrResponse) -> EntryDecision:
        self.calls.append(ocr.normalized_text)
        authorized = ocr.status == "recognized"
        return EntryDecision(
            correlation_id=ocr.correlation_id,
            decision="AUTHORIZED" if authorized else "MANUAL_REVIEW",
            reason="ACTIVE_MATCH" if authorized else "OCR_LOW_CONFIDENCE",
            message="The vehicle record permits entry at this time."
            if authorized
            else "Plate text confidence is too low; manual review is required.",
            normalized_plate=ocr.normalized_text,
            confidence=ocr.confidence,
            vehicle_id=None,
            evaluated_at=NOW,
        )


class FakeLogging:
    def __init__(self) -> None:
        self.calls = 0

    def persist(self, **values: object) -> DetectionLoggingResult:
        self.calls += 1
        decision = values["decision"]
        assert isinstance(decision, EntryDecision)
        snapshot = DecisionAuditSnapshot.from_entry_decision(decision)
        return DetectionLoggingResult(
            decision=snapshot,
            status="completed",
            failures=(),
            log_persisted=True,
            evidence=None,
            signed_access=None,
            completed_at=NOW,
        )


def service(
    candidates: list[PlateDetectionResponse],
    values: dict[str, tuple[str, float]],
    *,
    settings: Settings | None = None,
) -> tuple[RecognitionOrchestrationService, FakeOcr, FakeDecision, FakeLogging]:
    ocr = FakeOcr(values)
    decision = FakeDecision()
    logging = FakeLogging()
    return (
        RecognitionOrchestrationService(
            FakeDetector(detection(candidates)),  # type: ignore[arg-type]
            ocr,  # type: ignore[arg-type]
            decision,  # type: ignore[arg-type]
            logging,  # type: ignore[arg-type]
            settings=settings or Settings(),
        ),
        ocr,
        decision,
        logging,
    )


def test_ranking_is_order_independent_and_selects_best_reliable_candidate() -> None:
    first = candidate("first", confidence=0.80, bbox=(10, 10, 170, 50))
    second = candidate("second", confidence=0.96, bbox=(300, 10, 460, 50))
    values = {"first": ("YGN 5A-1234", 0.98), "second": ("MDY 3B-5678", 0.70)}

    service_a, _, _, _ = service([first, second], values)
    service_b, _, _, _ = service([second, first], values)

    result_a = service_a.analyze(b"image", CORRELATION_ID)
    result_b = service_b.analyze(b"image", CORRELATION_ID)

    assert result_a.selected is not None and result_a.selected.bbox.x1 == 10
    assert result_b.selected is not None and result_b.selected.bbox.x1 == 10
    assert result_a.ocr is not None and result_a.ocr.normalized_text == "YGN5A1234"


def test_candidate_work_is_bounded_by_configuration() -> None:
    candidates = [
        candidate(
            str(index),
            confidence=0.9 - index * 0.1,
            bbox=(index * 100, 10, index * 100 + 160, 50),
        )
        for index in range(4)
    ]
    values = {str(index): (f"YGN {index + 1}A-1234", 0.9) for index in range(4)}
    service_instance, ocr, _, _ = service(
        candidates,
        values,
        settings=Settings(MAX_RECOGNITION_CANDIDATES=2),
    )

    service_instance.analyze(b"image", CORRELATION_ID)

    assert len(ocr.calls) == 2


def test_watermark_and_unsupported_or_numeric_free_text_are_manual_review() -> None:
    for text, confidence in (
        ("ALAMY", 0.99),
        ("ABC 12-3456", 0.99),
        ("YGN ABCD", 0.99),
        ("YGN 5A-1234", 0.50),
    ):
        item = candidate("candidate", confidence=0.99, bbox=(10, 10, 170, 50))
        instance, _, _, _ = service([item], {"candidate": (text, confidence)})

        result = instance.analyze(b"image", CORRELATION_ID)

        assert result.decision is not None
        assert result.decision.decision == "MANUAL_REVIEW"


def test_supported_regions_and_separators_remain_reliable() -> None:
    for text in ("YGN 5A-1234", "MDY 3B-5678", "NPT 2D-3456"):
        item = candidate("candidate", confidence=0.99, bbox=(10, 10, 170, 50))
        instance, _, _, _ = service([item], {"candidate": (text, 0.99)})

        result = instance.analyze(b"image", CORRELATION_ID)

        assert result.decision is not None
        assert result.decision.decision == "AUTHORIZED"


def test_close_reliable_candidates_are_manual_review() -> None:
    first = candidate("first", confidence=0.90, bbox=(10, 10, 170, 50))
    second = candidate("second", confidence=0.90, bbox=(300, 10, 460, 50))
    values = {"first": ("YGN 5A-1234", 0.90), "second": ("MDY 3B-5678", 0.90)}
    instance, _, _, _ = service([first, second], values)

    result = instance.analyze(b"image", CORRELATION_ID)

    assert result.decision is not None
    assert result.decision.decision == "MANUAL_REVIEW"


def test_distinct_reliable_candidates_remain_manual_review_even_when_scores_differ() -> (
    None
):
    first = candidate("first", confidence=0.99, bbox=(10, 10, 170, 50))
    second = candidate("second", confidence=0.50, bbox=(300, 10, 460, 50))
    values = {"first": ("YGN 5A-1234", 0.99), "second": ("MDY 3B-5678", 0.90)}
    instance_a, _, _, _ = service([first, second], values)
    instance_b, _, _, _ = service([second, first], values)

    result_a = instance_a.analyze(b"image", CORRELATION_ID)
    result_b = instance_b.analyze(b"image", CORRELATION_ID)

    assert result_a.decision is not None
    assert result_a.decision.decision == "MANUAL_REVIEW"
    assert result_b.decision is not None
    assert result_b.decision.decision == "MANUAL_REVIEW"
    assert result_a.decision.reason == result_b.decision.reason == "OCR_LOW_CONFIDENCE"
    assert "first" not in result_a.__repr__()
    assert "second" not in result_a.__repr__()


def test_same_reliable_normalized_plate_is_not_multi_plate_ambiguity() -> None:
    first = candidate("first", confidence=0.80, bbox=(10, 10, 170, 50))
    second = candidate("second", confidence=0.99, bbox=(300, 10, 460, 50))
    values = {
        "first": ("YGN 5A-1234", 0.80),
        "second": ("YGN 5A-1234", 0.99),
    }
    instance, _, _, _ = service([first, second], values)

    result = instance.analyze(b"image", CORRELATION_ID)

    assert result.decision is not None
    assert result.decision.decision == "AUTHORIZED"
    assert result.ocr is not None
    assert result.ocr.normalized_text == "YGN5A1234"


def test_ambiguous_recognition_persists_once_without_alternative_leakage() -> None:
    first = candidate("first", confidence=0.90, bbox=(10, 10, 170, 50))
    second = candidate("second", confidence=0.90, bbox=(300, 10, 460, 50))
    values = {"first": ("YGN 5A-1234", 0.90), "second": ("MDY 3B-5678", 0.90)}
    instance, _, _, logging = service([first, second], values)

    result = instance.recognize(b"image", CORRELATION_ID)

    assert result.logging is not None
    assert result.logging.decision.decision == "MANUAL_REVIEW"
    assert logging.calls == 1
    assert "first" not in result.model_dump_json()
    assert "second" not in result.model_dump_json()


def test_no_candidate_is_nonpersisting_until_normal_recognition() -> None:
    instance, _, decision, logging = service([], {})

    analysis = instance.analyze(b"image", CORRELATION_ID)

    assert analysis.selected is None
    assert analysis.decision is None
    assert decision.calls == []
    assert logging.calls == 0


def test_unreliable_and_ambiguous_normal_recognition_persist_once() -> None:
    item = candidate("candidate", confidence=0.99, bbox=(10, 10, 170, 50))
    instance, _, _, logging = service([item], {"candidate": ("ALAMY", 0.99)})

    result = instance.recognize(b"image", CORRELATION_ID)

    assert result.logging is not None
    assert result.logging.log_persisted is True
    assert result.logging.decision.decision == "MANUAL_REVIEW"
    assert logging.calls == 1


def test_internal_analysis_does_not_create_logs_or_evidence() -> None:
    item = candidate("candidate", confidence=0.99, bbox=(10, 10, 170, 50))
    instance, _, _, logging = service([item], {"candidate": ("YGN 5A-1234", 0.99)})

    result = instance.analyze(b"image", CORRELATION_ID)

    assert result.decision is not None
    assert logging.calls == 0
