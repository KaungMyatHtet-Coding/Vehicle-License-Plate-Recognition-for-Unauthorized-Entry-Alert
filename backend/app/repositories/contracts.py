"""Typed Day 9 persistence boundaries without authorization decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from app.schemas.decision import DecisionReason, DecisionStatus

VehicleStatus = Literal["active", "inactive", "blocked"]
OcrStatus = Literal["recognized", "manual_review"]
OcrReviewReason = Literal["OCR_EMPTY", "OCR_LOW_CONFIDENCE"]


@dataclass(frozen=True)
class AuthorizedVehicleRecord:
    """Durable authorized-vehicle data; status interpretation belongs to Day 10."""

    id: UUID
    normalized_plate: str
    status: VehicleStatus
    valid_from: datetime | None
    valid_until: datetime | None
    created_at: datetime
    updated_at: datetime
    description: str | None = None


@dataclass(frozen=True)
class DetectionLogRecord:
    """Auditable OCR and Day 10 decision metadata."""

    id: UUID
    correlation_id: UUID
    raw_text: str
    normalized_text: str
    confidence: float | None
    ocr_status: OcrStatus
    review_reason: OcrReviewReason | None
    decision: DecisionStatus
    decision_reason: DecisionReason
    matched_vehicle_id: UUID | None
    evidence_bucket: str | None
    evidence_object_path: str | None
    timings: dict[str, float]
    created_at: datetime


@dataclass(frozen=True)
class SettingRecord:
    """One server-owned JSON-compatible setting."""

    key: str
    value: Any
    created_at: datetime
    updated_at: datetime


class RepositoryError(RuntimeError):
    """Stable repository failure that does not expose provider internals."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AuthorizedVehicleRepository(Protocol):
    """Lookup boundary consumed by the later decision milestone."""

    def get_by_normalized_plate(
        self, normalized_plate: str
    ) -> AuthorizedVehicleRecord | None: ...

    def add(self, record: AuthorizedVehicleRecord) -> None: ...


class DetectionLogRepository(Protocol):
    """Detection-log boundary consumed by the later logging milestone."""

    def get_by_correlation_id(
        self, correlation_id: UUID
    ) -> DetectionLogRecord | None: ...

    def add(self, record: DetectionLogRecord) -> None: ...


class SettingsRepository(Protocol):
    """Server-setting boundary; values are never client credentials."""

    def get(self, key: str) -> SettingRecord | None: ...

    def set(self, record: SettingRecord) -> None: ...
