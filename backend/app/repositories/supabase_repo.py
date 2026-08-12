"""Fail-closed Supabase repository mappings for the canonical local contract."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from supabase import Client
from postgrest.exceptions import APIError

from app.repositories.contracts import (
    AuthorizedVehicleRecord,
    DetectionLogRecord,
    RepositoryError,
)
from app.repositories.memory import (
    validate_authorized_vehicle_record,
    validate_detection_log_record,
)


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise RepositoryError(
            "REPOSITORY_TIMESTAMP_INVALID",
            "The timestamp must be timezone-aware.",
        )
    return value.isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp is not timezone-aware")
    return parsed


def _required_datetime(row: dict[str, Any], field: str) -> datetime:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RepositoryError("SUPABASE_ROW_INVALID", "Supabase row data is invalid.")
    try:
        parsed = _parse_iso(value)
    except (AttributeError, TypeError, ValueError, OverflowError):
        raise RepositoryError(
            "SUPABASE_ROW_INVALID", "Supabase row data is invalid."
        ) from None
    if parsed is None:
        raise RepositoryError("SUPABASE_ROW_INVALID", "Supabase row data is invalid.")
    return parsed


def _optional_datetime(row: dict[str, Any], field: str) -> datetime | None:
    value = row.get(field)
    if value is None:
        return None
    try:
        return _parse_iso(value)
    except (AttributeError, TypeError, ValueError, OverflowError):
        raise RepositoryError(
            "SUPABASE_ROW_INVALID", "Supabase row data is invalid."
        ) from None


def _is_unique_violation(error: Exception) -> bool:
    """Recognize only PostgREST's structured PostgreSQL unique code."""

    return isinstance(error, APIError) and error.code == "23505"


def _provider_failure(operation: str) -> RepositoryError:
    """Return a stable error without exposing URL, SQL, or provider details."""

    return RepositoryError("SUPABASE_ERROR", f"Supabase {operation} failed.")


def _require_schema_ready(schema_ready: bool) -> None:
    if not schema_ready:
        raise RepositoryError(
            "SUPABASE_SCHEMA_NOT_READY",
            "The Supabase schema readiness is unknown or incompatible.",
        )


def _vehicle_from_row(row: dict[str, Any]) -> AuthorizedVehicleRecord:
    try:
        record = AuthorizedVehicleRecord(
            id=UUID(row["id"]),
            normalized_plate=row["normalized_plate"],
            status=row["status"],
            valid_from=_optional_datetime(row, "valid_from"),
            valid_until=_optional_datetime(row, "valid_until"),
            description=row.get("description"),
            created_at=_required_datetime(row, "created_at"),
            updated_at=_required_datetime(row, "updated_at"),
        )
        validate_authorized_vehicle_record(record)
        return record
    except RepositoryError:
        raise
    except (KeyError, TypeError, ValueError):
        raise RepositoryError(
            "SUPABASE_ROW_INVALID", "Supabase row data is invalid."
        ) from None


def _vehicle_payload(record: AuthorizedVehicleRecord) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "normalized_plate": record.normalized_plate,
        "status": record.status,
        "valid_from": _to_iso(record.valid_from),
        "valid_until": _to_iso(record.valid_until),
        "description": record.description,
        "created_at": _to_iso(record.created_at),
        "updated_at": _to_iso(record.updated_at),
    }


class SupabaseAuthorizedVehicleRepository:
    """Map the canonical vehicle contract without implicit upserts."""

    def __init__(self, client: Client, *, schema_ready: bool = False) -> None:
        self._client = client
        self._schema_ready = schema_ready

    def get_by_normalized_plate(
        self, normalized_plate: str
    ) -> AuthorizedVehicleRecord | None:
        _require_schema_ready(self._schema_ready)
        try:
            result = (
                self._client.table("authorized_vehicles")
                .select("*")
                .eq("normalized_plate", normalized_plate)
                .execute()
            )
            return _vehicle_from_row(result.data[0]) if result.data else None
        except RepositoryError:
            raise
        except Exception:
            raise _provider_failure("vehicle lookup") from None

    def add(self, record: AuthorizedVehicleRecord) -> None:
        _require_schema_ready(self._schema_ready)
        validate_authorized_vehicle_record(record)
        try:
            self._client.table("authorized_vehicles").insert(
                _vehicle_payload(record)
            ).execute()
        except Exception as exc:
            if _is_unique_violation(exc):
                raise RepositoryError(
                    "REPOSITORY_PLATE_DUPLICATE",
                    "The normalized plate already exists.",
                ) from None
            raise _provider_failure("vehicle insert") from None

    def get_by_id(self, vehicle_id: UUID) -> AuthorizedVehicleRecord | None:
        _require_schema_ready(self._schema_ready)
        try:
            result = (
                self._client.table("authorized_vehicles")
                .select("*")
                .eq("id", str(vehicle_id))
                .execute()
            )
            return _vehicle_from_row(result.data[0]) if result.data else None
        except RepositoryError:
            raise
        except Exception:
            raise _provider_failure("vehicle lookup") from None

    def list_all(self) -> tuple[AuthorizedVehicleRecord, ...]:
        _require_schema_ready(self._schema_ready)
        try:
            result = (
                self._client.table("authorized_vehicles")
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )
            return tuple(_vehicle_from_row(row) for row in (result.data or []))
        except RepositoryError:
            raise
        except Exception:
            raise _provider_failure("vehicle listing") from None

    def update(self, record: AuthorizedVehicleRecord) -> None:
        _require_schema_ready(self._schema_ready)
        validate_authorized_vehicle_record(record)
        try:
            result = (
                self._client.table("authorized_vehicles")
                .update(_vehicle_payload(record))
                .eq("id", str(record.id))
                .execute()
            )
            if not result.data:
                raise RepositoryError(
                    "REPOSITORY_VEHICLE_NOT_FOUND",
                    "The vehicle record does not exist.",
                )
        except RepositoryError:
            raise
        except Exception as exc:
            if _is_unique_violation(exc):
                raise RepositoryError(
                    "REPOSITORY_PLATE_DUPLICATE",
                    "The normalized plate already exists.",
                ) from None
            raise _provider_failure("vehicle update") from None


def _detection_payload(record: DetectionLogRecord) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "correlation_id": str(record.correlation_id),
        "raw_text": record.raw_text,
        "normalized_text": record.normalized_text,
        "confidence": record.confidence,
        "ocr_status": record.ocr_status,
        "review_reason": record.review_reason,
        "decision": record.decision,
        "decision_reason": record.decision_reason,
        "matched_vehicle_id": (
            str(record.matched_vehicle_id)
            if record.matched_vehicle_id is not None
            else None
        ),
        "evidence_bucket": record.evidence_bucket,
        "evidence_object_path": record.evidence_object_path,
        "timings": dict(record.timings),
        "created_at": _to_iso(record.created_at),
    }


def _detection_from_row(row: dict[str, Any]) -> DetectionLogRecord:
    try:
        matched = row.get("matched_vehicle_id")
        record = DetectionLogRecord(
            id=UUID(row["id"]),
            correlation_id=UUID(row["correlation_id"]),
            raw_text=row.get("raw_text") or "",
            normalized_text=row.get("normalized_text") or "",
            confidence=row.get("confidence"),
            ocr_status=row["ocr_status"],
            review_reason=row.get("review_reason"),
            decision=row["decision"],
            decision_reason=row["decision_reason"],
            matched_vehicle_id=UUID(matched) if matched else None,
            evidence_bucket=row.get("evidence_bucket"),
            evidence_object_path=row.get("evidence_object_path"),
            timings=dict(row.get("timings") or {}),
            created_at=_required_datetime(row, "created_at"),
        )
        validate_detection_log_record(record)
        return record
    except RepositoryError:
        raise
    except (KeyError, TypeError, ValueError):
        raise RepositoryError(
            "SUPABASE_ROW_INVALID", "Supabase row data is invalid."
        ) from None


class SupabaseDetectionLogRepository:
    """Map the complete canonical detection-log contract."""

    def __init__(self, client: Client, *, schema_ready: bool = False) -> None:
        self._client = client
        self._schema_ready = schema_ready

    def add(self, record: DetectionLogRecord) -> None:
        _require_schema_ready(self._schema_ready)
        validate_detection_log_record(record)
        try:
            self._client.table("detection_logs").insert(
                _detection_payload(record)
            ).execute()
        except Exception:
            raise _provider_failure("detection-log insert") from None

    def get_by_correlation_id(self, correlation_id: UUID) -> DetectionLogRecord | None:
        _require_schema_ready(self._schema_ready)
        try:
            result = (
                self._client.table("detection_logs")
                .select("*")
                .eq("correlation_id", str(correlation_id))
                .execute()
            )
            return _detection_from_row(result.data[0]) if result.data else None
        except RepositoryError:
            raise
        except Exception:
            raise _provider_failure("detection-log lookup") from None

    def list_all(self) -> tuple[DetectionLogRecord, ...]:
        _require_schema_ready(self._schema_ready)
        try:
            result = (
                self._client.table("detection_logs")
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )
            return tuple(_detection_from_row(row) for row in (result.data or []))
        except RepositoryError:
            raise
        except Exception:
            raise _provider_failure("detection-log listing") from None
