"""Sanitized public contracts for Day 15 vehicle management."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

PublicVehicleStatus = Literal["ACTIVE", "INACTIVE", "BLOCKED"]


class VehicleWriteBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    plate_number: str = Field(min_length=1, max_length=32)
    description: str | None = Field(default=None, max_length=200)
    valid_from: AwareDatetime | None = None
    valid_until: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_until <= self.valid_from
        ):
            raise ValueError("valid_until must be later than valid_from")
        return self


class VehicleCreate(VehicleWriteBase):
    status: PublicVehicleStatus = "ACTIVE"


class VehicleUpdate(VehicleWriteBase):
    status: PublicVehicleStatus


class VehicleStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: PublicVehicleStatus


class AuthorizedVehiclePublic(BaseModel):
    id: UUID
    normalized_plate: str
    description: str | None
    status: PublicVehicleStatus
    valid_from: datetime | None
    valid_until: datetime | None
    created_at: datetime
    updated_at: datetime


class AuthorizedVehicleList(BaseModel):
    items: list[AuthorizedVehiclePublic]
    total_items: int
