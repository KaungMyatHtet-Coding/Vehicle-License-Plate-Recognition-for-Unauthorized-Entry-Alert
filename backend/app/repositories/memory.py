"""Thread-safe network-free repositories for tests and local development."""

from __future__ import annotations

import re
import threading
import json
import math
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.repositories.contracts import (
    AuthorizedVehicleRecord,
    DetectionLogRecord,
    RepositoryError,
    SettingRecord,
)

PLATE_PATTERN = re.compile(r"^[A-Z0-9]+$")
SETTING_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")
EVIDENCE_BUCKET_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")


def _validate_timestamp(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise RepositoryError(
            "REPOSITORY_TIMESTAMP_INVALID",
            f"{field} must contain a timezone-aware timestamp.",
        )


class InMemoryAuthorizedVehicleRepository:
    """Enforce the migration's normalized-plate uniqueness in memory."""

    def __init__(self) -> None:
        self._records: dict[str, AuthorizedVehicleRecord] = {}
        self._lock = threading.RLock()

    def get_by_normalized_plate(
        self, normalized_plate: str
    ) -> AuthorizedVehicleRecord | None:
        if not PLATE_PATTERN.fullmatch(normalized_plate):
            raise RepositoryError(
                "REPOSITORY_PLATE_INVALID",
                "The normalized plate must contain only uppercase ASCII letters and digits.",
            )
        with self._lock:
            return self._records.get(normalized_plate)

    def add(self, record: AuthorizedVehicleRecord) -> None:
        if not PLATE_PATTERN.fullmatch(record.normalized_plate):
            raise RepositoryError(
                "REPOSITORY_PLATE_INVALID",
                "The normalized plate must contain only uppercase ASCII letters and digits.",
            )
        if record.status not in ("active", "inactive", "blocked"):
            raise RepositoryError(
                "REPOSITORY_STATUS_INVALID", "The vehicle status is unsupported."
            )
        _validate_timestamp(record.created_at, "created_at")
        _validate_timestamp(record.updated_at, "updated_at")
        if record.valid_from is not None:
            _validate_timestamp(record.valid_from, "valid_from")
        if record.valid_until is not None:
            _validate_timestamp(record.valid_until, "valid_until")
        if (
            record.valid_from is not None
            and record.valid_until is not None
            and record.valid_until <= record.valid_from
        ):
            raise RepositoryError(
                "REPOSITORY_VALIDITY_INVALID",
                "valid_until must be later than valid_from.",
            )
        with self._lock:
            if record.normalized_plate in self._records:
                raise RepositoryError(
                    "REPOSITORY_PLATE_DUPLICATE",
                    "The normalized plate already exists.",
                )
            self._records[record.normalized_plate] = record


class InMemoryDetectionLogRepository:
    """Retain validated OCR logs without performing decisions or I/O."""

    def __init__(self) -> None:
        self._records: dict[UUID, DetectionLogRecord] = {}
        self._lock = threading.RLock()

    def get_by_correlation_id(self, correlation_id: UUID) -> DetectionLogRecord | None:
        with self._lock:
            record = self._records.get(correlation_id)
            return replace(record, timings=deepcopy(record.timings)) if record else None

    def add(self, record: DetectionLogRecord) -> None:
        if record.normalized_text and not PLATE_PATTERN.fullmatch(
            record.normalized_text
        ):
            raise RepositoryError(
                "REPOSITORY_PLATE_INVALID",
                "Normalized OCR text must contain only uppercase ASCII letters and digits.",
            )
        if record.confidence is not None and (
            isinstance(record.confidence, bool)
            or not isinstance(record.confidence, (int, float))
            or not math.isfinite(float(record.confidence))
            or not 0.0 <= float(record.confidence) <= 1.0
        ):
            raise RepositoryError(
                "REPOSITORY_CONFIDENCE_INVALID",
                "OCR confidence must be between zero and one.",
            )
        expected_reason = {
            "recognized": None,
            "manual_review": record.review_reason,
        }
        if (
            record.ocr_status not in expected_reason
            or (record.ocr_status == "recognized" and record.review_reason is not None)
            or (
                record.ocr_status == "manual_review"
                and record.review_reason not in ("OCR_EMPTY", "OCR_LOW_CONFIDENCE")
            )
        ):
            raise RepositoryError(
                "REPOSITORY_OCR_STATE_INVALID",
                "The OCR status and review reason are inconsistent.",
            )
        evidence_values = (record.evidence_bucket, record.evidence_object_path)
        if (evidence_values[0] is None) != (evidence_values[1] is None):
            raise RepositoryError(
                "REPOSITORY_EVIDENCE_INVALID",
                "Evidence bucket and object path must be set together.",
            )
        if record.evidence_object_path is not None and (
            not EVIDENCE_BUCKET_PATTERN.fullmatch(record.evidence_bucket or "")
            or not record.evidence_object_path
            or len(record.evidence_object_path) > 1024
            or record.evidence_object_path.startswith("/")
            or "\\" in record.evidence_object_path
            or ".." in record.evidence_object_path.split("/")
        ):
            raise RepositoryError(
                "REPOSITORY_EVIDENCE_INVALID",
                "The evidence object path must be relative and traversal-free.",
            )
        if not isinstance(record.timings, dict) or any(
            not isinstance(key, str)
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value < 0
            for key, value in record.timings.items()
        ):
            raise RepositoryError(
                "REPOSITORY_TIMINGS_INVALID",
                "Detection timings must contain non-negative numeric values.",
            )
        _validate_timestamp(record.created_at, "created_at")
        stored = replace(record, timings=deepcopy(record.timings))
        with self._lock:
            if record.correlation_id in self._records:
                raise RepositoryError(
                    "REPOSITORY_CORRELATION_DUPLICATE",
                    "The correlation identifier already exists.",
                )
            self._records[record.correlation_id] = stored


class InMemorySettingsRepository:
    """Store copied JSON-compatible settings without credentials or network I/O."""

    def __init__(self) -> None:
        self._records: dict[str, SettingRecord] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> SettingRecord | None:
        if not SETTING_KEY_PATTERN.fullmatch(key):
            raise RepositoryError(
                "REPOSITORY_SETTING_KEY_INVALID", "The setting key is invalid."
            )
        with self._lock:
            record = self._records.get(key)
            return replace(record, value=deepcopy(record.value)) if record else None

    def set(self, record: SettingRecord) -> None:
        if not SETTING_KEY_PATTERN.fullmatch(record.key):
            raise RepositoryError(
                "REPOSITORY_SETTING_KEY_INVALID", "The setting key is invalid."
            )
        _validate_timestamp(record.created_at, "created_at")
        _validate_timestamp(record.updated_at, "updated_at")
        try:
            json.dumps(record.value, allow_nan=False)
            copied_value: Any = deepcopy(record.value)
        except (TypeError, ValueError) as exc:
            raise RepositoryError(
                "REPOSITORY_SETTING_VALUE_INVALID",
                "The setting value could not be copied safely.",
            ) from exc
        stored = replace(record, value=copied_value)
        with self._lock:
            self._records[record.key] = stored


def utc_now() -> datetime:
    """Return a timezone-aware timestamp for fixtures and adapters."""

    return datetime.now(timezone.utc)
