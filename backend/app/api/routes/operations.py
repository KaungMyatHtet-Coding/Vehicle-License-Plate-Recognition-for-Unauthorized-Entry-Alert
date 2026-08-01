"""Sanitized Day 14 operational read endpoints."""

import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime

from app.dependencies import get_application_dependencies
from app.schemas.decision import DecisionStatus
from app.schemas.operations import (
    DashboardStatistics,
    DetectionDetail,
    PaginatedAlerts,
    PaginatedDetections,
)
from app.services.detection_queries import DetectionQueryService

router = APIRouter(tags=["operations"])


def get_detection_query_service() -> DetectionQueryService:
    dependencies = get_application_dependencies()
    return DetectionQueryService(
        dependencies.detection_logs, dependencies.recognition_activity
    )


@router.get("/detections", response_model=PaginatedDetections)
def list_detections(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    decision: DecisionStatus | None = None,
    normalized_plate: Annotated[str | None, Query(min_length=1, max_length=32)] = None,
    created_from: AwareDatetime | None = None,
    created_to: AwareDatetime | None = None,
    service: DetectionQueryService = Depends(get_detection_query_service),
) -> PaginatedDetections:
    if (
        normalized_plate is not None
        and re.fullmatch(r"[A-Z0-9]+", normalized_plate) is None
    ):
        raise HTTPException(
            status_code=422, detail="The normalized plate filter is invalid."
        )
    if (
        created_from is not None
        and created_to is not None
        and created_to <= created_from
    ):
        raise HTTPException(status_code=422, detail="The date range is invalid.")
    try:
        return service.history(
            page=page,
            page_size=page_size,
            decision=decision,
            normalized_plate=normalized_plate,
            created_from=created_from,
            created_to=created_to,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Detection history is temporarily unavailable."
        ) from exc


@router.get("/detections/{correlation_id}", response_model=DetectionDetail)
def get_detection(
    correlation_id: UUID,
    service: DetectionQueryService = Depends(get_detection_query_service),
) -> DetectionDetail:
    try:
        result = service.detail(correlation_id)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Detection history is temporarily unavailable."
        ) from exc
    if result is None:
        raise HTTPException(
            status_code=404, detail="The detection record was not found."
        )
    return result


@router.get("/dashboard/statistics", response_model=DashboardStatistics)
def get_statistics(
    service: DetectionQueryService = Depends(get_detection_query_service),
) -> DashboardStatistics:
    try:
        return service.statistics()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Dashboard statistics are temporarily unavailable."
        ) from exc


@router.get("/alerts", response_model=PaginatedAlerts)
def list_alerts(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    service: DetectionQueryService = Depends(get_detection_query_service),
) -> PaginatedAlerts:
    try:
        return service.alerts(page=page, page_size=page_size)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="Alerts are temporarily unavailable."
        ) from exc
