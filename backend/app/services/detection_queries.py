"""Server-authoritative Day 14 history, statistics, and alert queries."""

from collections.abc import Callable
from datetime import datetime, time, timedelta, timezone
import math
from uuid import UUID

from app.repositories.contracts import (
    DetectionLogRecord,
    DetectionLogRepository,
    RecognitionActivityRepository,
)
from app.schemas.decision import DecisionStatus
from app.schemas.operations import (
    AlertSummary,
    DashboardStatistics,
    DetectionDetail,
    DetectionSummary,
    PaginatedAlerts,
    PaginatedDetections,
    TrendBucket,
)

REASON_MESSAGES = {
    "ACTIVE_MATCH": "An active vehicle record permitted entry.",
    "VEHICLE_NOT_FOUND": "No currently permitting vehicle record was found.",
    "VEHICLE_INACTIVE": "The matching vehicle record is inactive.",
    "VEHICLE_BLOCKED": "The matching vehicle record does not permit entry.",
    "VEHICLE_NOT_YET_VALID": "The vehicle record is not valid yet.",
    "VEHICLE_EXPIRED": "The vehicle record has expired.",
    "OCR_EMPTY": "No reliable plate text was available.",
    "OCR_LOW_CONFIDENCE": "Plate text confidence requires manual review.",
    "OCR_RESULT_INVALID": "The OCR result requires manual review.",
    "PLATE_REGION_MISSING": "The plate region could not be confirmed.",
    "PLATE_FORMAT_UNSUPPORTED": "The plate format requires manual review.",
    "PLATE_TEXT_UNRELIABLE": "The detected text is not reliable plate text.",
    "MULTIPLE_PLATES_AMBIGUOUS": "Multiple plate candidates require manual review.",
    "DECISION_TIME_INVALID": "The decision time requires manual review.",
    "VEHICLE_RECORD_INVALID": "The vehicle record requires manual review.",
    "VEHICLE_LOOKUP_FAILED": "Vehicle lookup was unavailable; manual review is required.",
}


class DetectionQueryService:
    def __init__(
        self,
        logs: DetectionLogRepository,
        activity: RecognitionActivityRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._logs = logs
        self._activity = activity
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _summary(record: DetectionLogRecord) -> DetectionSummary:
        return DetectionSummary(
            correlation_id=str(record.correlation_id),
            decision=record.decision,
            reason=record.decision_reason,
            reason_message=REASON_MESSAGES[record.decision_reason],
            normalized_plate=record.normalized_text,
            confidence=record.confidence,
            created_at=record.created_at,
            evidence_available=record.evidence_object_path is not None,
        )

    def history(
        self,
        *,
        page: int,
        page_size: int,
        decision: DecisionStatus | None = None,
        normalized_plate: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> PaginatedDetections:
        records = list(self._logs.list_all())
        if decision is not None:
            records = [item for item in records if item.decision == decision]
        if normalized_plate is not None:
            records = [
                item for item in records if item.normalized_text == normalized_plate
            ]
        if created_from is not None:
            records = [item for item in records if item.created_at >= created_from]
        if created_to is not None:
            records = [item for item in records if item.created_at < created_to]
        total = len(records)
        start = (page - 1) * page_size
        return PaginatedDetections(
            items=tuple(
                self._summary(item) for item in records[start : start + page_size]
            ),
            page=page,
            page_size=page_size,
            total_items=total,
            total_pages=math.ceil(total / page_size) if total else 0,
        )

    def detail(self, correlation_id: UUID) -> DetectionDetail | None:
        record = self._logs.get_by_correlation_id(correlation_id)
        if record is None:
            return None
        summary = self._summary(record)
        return DetectionDetail(**summary.model_dump(), timings=dict(record.timings))

    def statistics(self) -> DashboardStatistics:
        logs = self._logs.list_all()
        no_plate = self._activity.list_no_plate()
        counts = {"AUTHORIZED": 0, "UNAUTHORIZED": 0, "MANUAL_REVIEW": 0}
        for record in logs:
            counts[record.decision] += 1
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("statistics clock must be timezone-aware")
        today = datetime.combine(
            now.astimezone(timezone.utc).date(), time.min, tzinfo=timezone.utc
        )
        starts = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
        trend: list[TrendBucket] = []
        for start in starts:
            end = start + timedelta(days=1)
            selected = [
                item
                for item in logs
                if start <= item.created_at.astimezone(timezone.utc) < end
            ]
            missing = sum(
                1
                for _, created_at in no_plate
                if start <= created_at.astimezone(timezone.utc) < end
            )
            trend.append(
                TrendBucket(
                    bucket_start=start,
                    authorized=sum(item.decision == "AUTHORIZED" for item in selected),
                    unauthorized=sum(
                        item.decision == "UNAUTHORIZED" for item in selected
                    ),
                    manual_review=sum(
                        item.decision == "MANUAL_REVIEW" for item in selected
                    ),
                    no_plate=missing,
                    total=len(selected) + missing,
                )
            )
        return DashboardStatistics(
            total_recognitions=len(logs) + len(no_plate),
            authorized=counts["AUTHORIZED"],
            unauthorized=counts["UNAUTHORIZED"],
            manual_review=counts["MANUAL_REVIEW"],
            no_plate=len(no_plate),
            trend=tuple(trend),
        )

    def alerts(self, *, page: int, page_size: int) -> PaginatedAlerts:
        records = [
            item
            for item in self._logs.list_all()
            if item.decision in {"UNAUTHORIZED", "MANUAL_REVIEW"}
        ]
        total = len(records)
        start = (page - 1) * page_size
        return PaginatedAlerts(
            items=tuple(
                AlertSummary(
                    **self._summary(item).model_dump(),
                    alert_type=(
                        "ENTRY_NOT_AUTHORIZED"
                        if item.decision == "UNAUTHORIZED"
                        else "MANUAL_REVIEW"
                    ),
                    message=(
                        "This record did not permit entry and may require operator review."
                        if item.decision == "UNAUTHORIZED"
                        else "This record requires operator review before entry decisions."
                    ),
                )
                for item in records[start : start + page_size]
            ),
            page=page,
            page_size=page_size,
            total_items=total,
            total_pages=math.ceil(total / page_size) if total else 0,
        )
