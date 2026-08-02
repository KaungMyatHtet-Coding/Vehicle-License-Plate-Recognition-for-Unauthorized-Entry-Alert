"""Authoritative Day 15 authorized-vehicle management service."""

from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.repositories.contracts import (
    AuthorizedVehicleRecord,
    AuthorizedVehicleRepository,
    RepositoryError,
)
from app.schemas.vehicles import (
    AuthorizedVehiclePublic,
    PublicVehicleStatus,
    VehicleCreate,
    VehicleUpdate,
)
from app.services.ocr_recognition import normalize_plate_text


class VehicleManagementError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code


def _public(record: AuthorizedVehicleRecord) -> AuthorizedVehiclePublic:
    return AuthorizedVehiclePublic(
        id=record.id,
        normalized_plate=record.normalized_plate,
        description=record.description,
        status=record.status.upper(),
        valid_from=record.valid_from,
        valid_until=record.valid_until,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class VehicleManagementService:
    def __init__(
        self,
        repository: AuthorizedVehicleRepository,
        clock=lambda: datetime.now(timezone.utc),
    ) -> None:
        self.repository = repository
        self.clock = clock

    @staticmethod
    def normalized(value: str) -> str:
        result = normalize_plate_text(value)
        if not result or len(result) > 32:
            raise VehicleManagementError("VEHICLE_PLATE_INVALID")
        return result

    def list(
        self, search: str | None = None, status: PublicVehicleStatus | None = None
    ) -> list[AuthorizedVehiclePublic]:
        term = self.normalized(search) if search else None
        records = self.repository.list_all()
        return [
            _public(item)
            for item in records
            if (term is None or term in item.normalized_plate)
            and (status is None or item.status == status.lower())
        ]

    def get(self, vehicle_id: UUID) -> AuthorizedVehiclePublic | None:
        record = self.repository.get_by_id(vehicle_id)
        return _public(record) if record else None

    def create(self, data: VehicleCreate) -> AuthorizedVehiclePublic:
        now = self.clock()
        record = AuthorizedVehicleRecord(
            id=uuid4(),
            normalized_plate=self.normalized(data.plate_number),
            status=data.status.lower(),
            valid_from=data.valid_from,
            valid_until=data.valid_until,
            created_at=now,
            updated_at=now,
            description=data.description or None,
        )
        try:
            self.repository.add(record)
        except RepositoryError as exc:
            raise VehicleManagementError(
                "VEHICLE_DUPLICATE"
                if exc.code == "REPOSITORY_PLATE_DUPLICATE"
                else "VEHICLE_WRITE_FAILED"
            ) from exc
        return _public(record)

    def update(
        self, vehicle_id: UUID, data: VehicleUpdate
    ) -> AuthorizedVehiclePublic | None:
        previous = self.repository.get_by_id(vehicle_id)
        if previous is None:
            return None
        record = replace(
            previous,
            normalized_plate=self.normalized(data.plate_number),
            status=data.status.lower(),
            valid_from=data.valid_from,
            valid_until=data.valid_until,
            description=data.description or None,
            updated_at=self.clock(),
        )
        try:
            self.repository.update(record)
        except RepositoryError as exc:
            raise VehicleManagementError(
                "VEHICLE_DUPLICATE"
                if exc.code == "REPOSITORY_PLATE_DUPLICATE"
                else "VEHICLE_WRITE_FAILED"
            ) from exc
        return _public(record)

    def status(
        self, vehicle_id: UUID, status: PublicVehicleStatus
    ) -> AuthorizedVehiclePublic | None:
        previous = self.repository.get_by_id(vehicle_id)
        if previous is None:
            return None
        record = replace(previous, status=status.lower(), updated_at=self.clock())
        try:
            self.repository.update(record)
        except RepositoryError as exc:
            raise VehicleManagementError("VEHICLE_WRITE_FAILED") from exc
        return _public(record)
