"""Private evidence-storage boundary and network-free in-memory adapter."""

from __future__ import annotations

import hashlib
import re
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from app.schemas.logging import EvidenceReference, SignedEvidenceAccess

BUCKET_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")


class EvidenceStorageError(RuntimeError):
    """Stable private-storage failure without provider details."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def validate_evidence_location(bucket: str, object_path: str) -> None:
    """Reject unsafe bucket names and non-relative object paths."""

    if (
        not isinstance(bucket, str)
        or not BUCKET_PATTERN.fullmatch(bucket)
        or not isinstance(object_path, str)
        or not 1 <= len(object_path) <= 1024
        or object_path.startswith("/")
        or "\\" in object_path
        or ".." in object_path.split("/")
        or re.match(r"^[A-Za-z]:", object_path)
    ):
        raise EvidenceStorageError(
            "EVIDENCE_LOCATION_INVALID",
            "The private evidence location is invalid.",
        )


@dataclass(frozen=True)
class StoredEvidence:
    """Immutable storage confirmation for one private JPEG object."""

    reference: EvidenceReference
    byte_count: int
    sha256: str


@dataclass(frozen=True)
class DeletedEvidence:
    """Authoritative confirmation of one removed private object."""

    reference: EvidenceReference


class EvidenceStorage(Protocol):
    """Minimal private object-storage operations used by Day 11."""

    def store(
        self, bucket: str, object_path: str, content: bytes, content_type: str
    ) -> StoredEvidence: ...

    def delete(self, bucket: str, object_path: str) -> DeletedEvidence: ...

    def exists(self, bucket: str, object_path: str) -> bool: ...

    def create_signed_access(
        self, bucket: str, object_path: str, lifetime_seconds: int
    ) -> SignedEvidenceAccess: ...

    def resolve_signed_access(self, token: str) -> bytes: ...


class InMemoryEvidenceStorage:
    """Thread-safe private storage for tests without filesystem or network I/O."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._objects: dict[tuple[str, str], bytes] = {}
        self._grants: dict[str, tuple[tuple[str, str], datetime]] = {}
        self._lock = threading.RLock()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def store(
        self, bucket: str, object_path: str, content: bytes, content_type: str
    ) -> StoredEvidence:
        validate_evidence_location(bucket, object_path)
        if (
            content_type != "image/jpeg"
            or not isinstance(content, bytes)
            or not content
        ):
            raise EvidenceStorageError(
                "EVIDENCE_CONTENT_INVALID",
                "The evidence content is invalid.",
            )
        key = (bucket, object_path)
        copied = bytes(content)
        with self._lock:
            if key in self._objects:
                raise EvidenceStorageError(
                    "EVIDENCE_OBJECT_EXISTS",
                    "The evidence object already exists.",
                )
            self._objects[key] = copied
        return StoredEvidence(
            reference=EvidenceReference(bucket=bucket, object_path=object_path),
            byte_count=len(copied),
            sha256=hashlib.sha256(copied).hexdigest(),
        )

    def delete(self, bucket: str, object_path: str) -> DeletedEvidence:
        validate_evidence_location(bucket, object_path)
        key = (bucket, object_path)
        with self._lock:
            if self._objects.pop(key, None) is None:
                raise EvidenceStorageError(
                    "EVIDENCE_OBJECT_MISSING",
                    "The evidence object is unavailable.",
                )
            self._grants = {
                token: grant for token, grant in self._grants.items() if grant[0] != key
            }
        return DeletedEvidence(
            reference=EvidenceReference(bucket=bucket, object_path=object_path)
        )

    def exists(self, bucket: str, object_path: str) -> bool:
        """Report whether one private object currently exists."""

        validate_evidence_location(bucket, object_path)
        with self._lock:
            return (bucket, object_path) in self._objects

    def create_signed_access(
        self, bucket: str, object_path: str, lifetime_seconds: int
    ) -> SignedEvidenceAccess:
        validate_evidence_location(bucket, object_path)
        if (
            isinstance(lifetime_seconds, bool)
            or not isinstance(lifetime_seconds, int)
            or not 60 <= lifetime_seconds <= 3600
        ):
            raise EvidenceStorageError(
                "EVIDENCE_SIGNED_LIFETIME_INVALID",
                "The signed-access lifetime is invalid.",
            )
        with self._lock:
            key = (bucket, object_path)
            if key not in self._objects:
                raise EvidenceStorageError(
                    "EVIDENCE_OBJECT_MISSING",
                    "The evidence object is unavailable.",
                )
            now = self._safe_now()
            expires_at = now + timedelta(seconds=lifetime_seconds)
            token = secrets.token_urlsafe(32)
            self._grants[token] = (key, expires_at)
            return SignedEvidenceAccess(token=token, expires_at=expires_at)

    def resolve_signed_access(self, token: str) -> bytes:
        """Resolve one opaque, unexpired grant to defensive evidence bytes."""

        if not isinstance(token, str) or not token:
            raise EvidenceStorageError(
                "EVIDENCE_GRANT_INVALID",
                "The signed evidence grant is invalid.",
            )
        with self._lock:
            grant = self._grants.get(token)
            if grant is None:
                raise EvidenceStorageError(
                    "EVIDENCE_GRANT_INVALID",
                    "The signed evidence grant is invalid.",
                )
            key, expires_at = grant
            if self._safe_now() >= expires_at:
                self._grants.pop(token, None)
                raise EvidenceStorageError(
                    "EVIDENCE_GRANT_EXPIRED",
                    "The signed evidence grant has expired.",
                )
            content = self._objects.get(key)
            if content is None:
                self._grants.pop(token, None)
                raise EvidenceStorageError(
                    "EVIDENCE_GRANT_INVALID",
                    "The signed evidence grant is invalid.",
                )
            return bytes(bytearray(content))

    def _safe_now(self) -> datetime:
        try:
            value = self._clock()
        except Exception as exc:
            raise EvidenceStorageError(
                "EVIDENCE_TIME_INVALID",
                "The evidence clock is unavailable.",
            ) from exc
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise EvidenceStorageError(
                "EVIDENCE_TIME_INVALID",
                "The evidence clock is unavailable.",
            )
        return value

    def get_for_test(self, bucket: str, object_path: str) -> bytes | None:
        """Return a defensive copy for network-free integration assertions."""

        validate_evidence_location(bucket, object_path)
        with self._lock:
            content = self._objects.get((bucket, object_path))
            return bytes(bytearray(content)) if content is not None else None
