"""Supabase persistence implementation for live database integration."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from supabase import Client

from app.repositories.contracts import (
    AuthorizedVehicleRecord,
    DetectionLogRecord,
    RepositoryError,
)


def _to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _parse_iso(val: str | None) -> datetime | None:
    if not val:
        return None
    dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class SupabaseAuthorizedVehicleRepository:
    """Live database repository for authorized vehicles using Supabase."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def get_by_normalized_plate(
        self, normalized_plate: str
    ) -> AuthorizedVehicleRecord | None:
        try:
            res = (
                self._client.table("authorized_vehicles")
                .select("*")
                .eq("plate_number", normalized_plate)
                .execute()
            )
            if not res.data:
                return None
            row = res.data[0]
            return AuthorizedVehicleRecord(
                id=UUID(row["id"]),
                normalized_plate=row["plate_number"],
                status=row["status"].lower(),  # type: ignore[arg-type]
                valid_from=_parse_iso(row.get("valid_from")),
                valid_until=_parse_iso(row.get("valid_until")),
                description=row.get("description"),
                created_at=_parse_iso(row["created_at"]) or datetime.now(timezone.utc),
                updated_at=_parse_iso(row["updated_at"]) or datetime.now(timezone.utc),
            )
        except Exception as exc:
            raise RepositoryError(
                "SUPABASE_ERROR", f"Failed to fetch vehicle: {exc}"
            ) from exc

    def add(self, record: AuthorizedVehicleRecord) -> None:
        try:
            payload = {
                "id": str(record.id),
                "plate_number": record.normalized_plate,
                "status": record.status.upper(),
                "valid_from": _to_iso(record.valid_from),
                "valid_until": _to_iso(record.valid_until),
                "description": record.description,
                "created_at": _to_iso(record.created_at),
                "updated_at": _to_iso(record.updated_at),
            }
            self._client.table("authorized_vehicles").upsert(payload).execute()
        except Exception as exc:
            raise RepositoryError(
                "SUPABASE_ERROR", f"Failed to save vehicle: {exc}"
            ) from exc

    def get_by_id(self, vehicle_id: UUID) -> AuthorizedVehicleRecord | None:
        try:
            res = (
                self._client.table("authorized_vehicles")
                .select("*")
                .eq("id", str(vehicle_id))
                .execute()
            )
            if not res.data:
                return None
            row = res.data[0]
            return AuthorizedVehicleRecord(
                id=UUID(row["id"]),
                normalized_plate=row["plate_number"],
                status=row["status"].lower(),  # type: ignore[arg-type]
                valid_from=_parse_iso(row.get("valid_from")),
                valid_until=_parse_iso(row.get("valid_until")),
                description=row.get("description"),
                created_at=_parse_iso(row["created_at"]) or datetime.now(timezone.utc),
                updated_at=_parse_iso(row["updated_at"]) or datetime.now(timezone.utc),
            )
        except Exception as exc:
            raise RepositoryError(
                "SUPABASE_ERROR", f"Failed to get vehicle by ID: {exc}"
            ) from exc

    def list_all(self) -> tuple[AuthorizedVehicleRecord, ...]:
        try:
            res = (
                self._client.table("authorized_vehicles")
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )
            records = []
            for row in res.data or []:
                records.append(
                    AuthorizedVehicleRecord(
                        id=UUID(row["id"]),
                        normalized_plate=row["plate_number"],
                        status=row["status"].lower(),  # type: ignore[arg-type]
                        valid_from=_parse_iso(row.get("valid_from")),
                        valid_until=_parse_iso(row.get("valid_until")),
                        description=row.get("description"),
                        created_at=_parse_iso(row["created_at"])
                        or datetime.now(timezone.utc),
                        updated_at=_parse_iso(row["updated_at"])
                        or datetime.now(timezone.utc),
                    )
                )
            return tuple(records)
        except Exception as exc:
            raise RepositoryError(
                "SUPABASE_ERROR", f"Failed to list vehicles: {exc}"
            ) from exc

    def clear(self) -> None:
        try:
            self._client.table("authorized_vehicles").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        except Exception:
            pass

    def update(self, record: AuthorizedVehicleRecord) -> None:
        self.add(record)


class SupabaseDetectionLogRepository:
    """Live database repository for detection logs using Supabase."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def clear(self) -> None:
        try:
            self._client.table("detection_logs").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        except Exception:
            pass

    def add(self, record: DetectionLogRecord) -> None:
        try:
            payload = {
                "id": str(record.id),
                "correlation_id": str(record.correlation_id),
                "timestamp": _to_iso(record.created_at),
                "normalized_plate": record.normalized_text or None,
                "raw_ocr_text": record.raw_text,
                "confidence": record.confidence,
                "decision": record.decision,
                "reason_code": record.decision_reason,
                "evidence_storage_path": record.evidence_object_path,
                "created_at": _to_iso(record.created_at),
            }
            self._client.table("detection_logs").insert(payload).execute()
        except Exception as exc:
            raise RepositoryError(
                "SUPABASE_ERROR", f"Failed to log detection: {exc}"
            ) from exc

    def get_by_correlation_id(self, correlation_id: UUID) -> DetectionLogRecord | None:
        try:
            res = (
                self._client.table("detection_logs")
                .select("*")
                .eq("correlation_id", str(correlation_id))
                .execute()
            )
            if not res.data:
                return None
            row = res.data[0]
            return DetectionLogRecord(
                id=UUID(row["id"]),
                correlation_id=UUID(row["correlation_id"]),
                raw_text=row.get("raw_ocr_text") or "",
                normalized_text=row.get("normalized_plate") or "",
                confidence=row.get("confidence"),
                ocr_status="recognized"
                if row.get("normalized_plate")
                else "manual_review",
                review_reason=None,
                decision=row["decision"],
                decision_reason=row["reason_code"],
                matched_vehicle_id=None,
                evidence_bucket="detection-evidence",
                evidence_object_path=row.get("evidence_storage_path"),
                timings={},
                created_at=_parse_iso(row["created_at"]) or datetime.now(timezone.utc),
            )
        except Exception as exc:
            raise RepositoryError(
                "SUPABASE_ERROR", f"Failed to get log: {exc}"
            ) from exc

    def list_all(self) -> tuple[DetectionLogRecord, ...]:
        try:
            res = (
                self._client.table("detection_logs")
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )
            records = []
            for row in res.data or []:
                records.append(
                    DetectionLogRecord(
                        id=UUID(row["id"]),
                        correlation_id=UUID(row["correlation_id"]),
                        raw_text=row.get("raw_ocr_text") or "",
                        normalized_text=row.get("normalized_plate") or "",
                        confidence=row.get("confidence"),
                        ocr_status="recognized"
                        if row.get("normalized_plate")
                        else "manual_review",
                        review_reason=None,
                        decision=row["decision"],
                        decision_reason=row["reason_code"],
                        matched_vehicle_id=None,
                        evidence_bucket="detection-evidence",
                        evidence_object_path=row.get("evidence_storage_path"),
                        timings={},
                        created_at=_parse_iso(row["created_at"])
                        or datetime.now(timezone.utc),
                    )
                )
            return tuple(records)
        except Exception as exc:
            raise RepositoryError(
                "SUPABASE_ERROR", f"Failed to list logs: {exc}"
            ) from exc
