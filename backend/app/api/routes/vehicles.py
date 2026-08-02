"""Validated and sanitized Day 15 authorized-vehicle endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_application_dependencies
from app.schemas.vehicles import (
    AuthorizedVehicleList,
    AuthorizedVehiclePublic,
    PublicVehicleStatus,
    VehicleCreate,
    VehicleStatusUpdate,
    VehicleUpdate,
)
from app.services.vehicle_management import (
    VehicleManagementError,
    VehicleManagementService,
)

router = APIRouter(prefix="/authorized-vehicles", tags=["authorized vehicles"])


def get_service() -> VehicleManagementService:
    return VehicleManagementService(get_application_dependencies().vehicles)


def _failure(exc: VehicleManagementError) -> HTTPException:
    if exc.code == "VEHICLE_DUPLICATE":
        return HTTPException(
            status_code=409,
            detail="An authorized vehicle with that normalized plate already exists.",
        )
    if exc.code == "VEHICLE_PLATE_INVALID":
        return HTTPException(status_code=422, detail="The plate number is invalid.")
    return HTTPException(
        status_code=503,
        detail="Authorized vehicle management is temporarily unavailable.",
    )


@router.get("", response_model=AuthorizedVehicleList)
def list_vehicles(
    search: Annotated[str | None, Query(min_length=1, max_length=32)] = None,
    status_filter: PublicVehicleStatus | None = None,
    service: VehicleManagementService = Depends(get_service),
) -> AuthorizedVehicleList:
    try:
        items = service.list(search, status_filter)
        return AuthorizedVehicleList(items=items, total_items=len(items))
    except VehicleManagementError as exc:
        raise _failure(exc) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Authorized vehicle management is temporarily unavailable.",
        ) from exc


@router.get("/{vehicle_id}", response_model=AuthorizedVehiclePublic)
def get_vehicle(
    vehicle_id: UUID, service: VehicleManagementService = Depends(get_service)
) -> AuthorizedVehiclePublic:
    try:
        result = service.get(vehicle_id)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Authorized vehicle management is temporarily unavailable.",
        ) from exc
    if result is None:
        raise HTTPException(
            status_code=404, detail="The authorized vehicle was not found."
        )
    return result


@router.post(
    "", response_model=AuthorizedVehiclePublic, status_code=status.HTTP_201_CREATED
)
def create_vehicle(
    data: VehicleCreate, service: VehicleManagementService = Depends(get_service)
) -> AuthorizedVehiclePublic:
    try:
        return service.create(data)
    except VehicleManagementError as exc:
        raise _failure(exc) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Authorized vehicle management is temporarily unavailable.",
        ) from exc


@router.put("/{vehicle_id}", response_model=AuthorizedVehiclePublic)
def update_vehicle(
    vehicle_id: UUID,
    data: VehicleUpdate,
    service: VehicleManagementService = Depends(get_service),
) -> AuthorizedVehiclePublic:
    try:
        result = service.update(vehicle_id, data)
    except VehicleManagementError as exc:
        raise _failure(exc) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Authorized vehicle management is temporarily unavailable.",
        ) from exc
    if result is None:
        raise HTTPException(
            status_code=404, detail="The authorized vehicle was not found."
        )
    return result


@router.patch("/{vehicle_id}/status", response_model=AuthorizedVehiclePublic)
def update_vehicle_status(
    vehicle_id: UUID,
    data: VehicleStatusUpdate,
    service: VehicleManagementService = Depends(get_service),
) -> AuthorizedVehiclePublic:
    try:
        result = service.status(vehicle_id, data.status)
    except VehicleManagementError as exc:
        raise _failure(exc) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Authorized vehicle management is temporarily unavailable.",
        ) from exc
    if result is None:
        raise HTTPException(
            status_code=404, detail="The authorized vehicle was not found."
        )
    return result
