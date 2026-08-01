"""Sanitized public schemas for Day 14 operational views."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.schemas.decision import DecisionReason, DecisionStatus


class DetectionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correlation_id: str
    decision: DecisionStatus
    reason: DecisionReason
    reason_message: str
    normalized_plate: str
    confidence: float | None
    created_at: AwareDatetime
    evidence_available: bool


class DetectionDetail(DetectionSummary):
    timings: dict[str, float]
    evidence_access: Literal["restricted"] = "restricted"


class PaginatedDetections(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: tuple[DetectionSummary, ...]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    timezone: Literal["UTC"] = "UTC"


class TrendBucket(BaseModel):
    bucket_start: AwareDatetime
    authorized: int = Field(ge=0)
    unauthorized: int = Field(ge=0)
    manual_review: int = Field(ge=0)
    no_plate: int = Field(ge=0)
    total: int = Field(ge=0)


class DashboardStatistics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_recognitions: int = Field(ge=0)
    authorized: int = Field(ge=0)
    unauthorized: int = Field(ge=0)
    manual_review: int = Field(ge=0)
    no_plate: int = Field(ge=0)
    timezone: Literal["UTC"] = "UTC"
    trend_granularity: Literal["day"] = "day"
    trend: tuple[TrendBucket, ...]


class AlertSummary(DetectionSummary):
    alert_type: Literal["ENTRY_NOT_AUTHORIZED"] = "ENTRY_NOT_AUTHORIZED"
    message: str = "This record did not permit entry and may require operator review."


class PaginatedAlerts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: tuple[AlertSummary, ...]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    timezone: Literal["UTC"] = "UTC"
