"""Shared process-local application dependencies.

These adapters are intentionally volatile and are not Supabase integration.
"""

from dataclasses import dataclass
import threading

from app.repositories.memory import (
    InMemoryAuthorizedVehicleRepository,
    InMemoryDetectionLogRepository,
    InMemoryRecognitionActivityRepository,
)
from app.services.evidence_storage import InMemoryEvidenceStorage


@dataclass(frozen=True)
class ApplicationDependencies:
    vehicles: InMemoryAuthorizedVehicleRepository
    detection_logs: InMemoryDetectionLogRepository
    recognition_activity: InMemoryRecognitionActivityRepository
    evidence_storage: InMemoryEvidenceStorage


_dependencies: ApplicationDependencies | None = None
_lock = threading.Lock()


def get_application_dependencies() -> ApplicationDependencies:
    global _dependencies
    if _dependencies is None:
        with _lock:
            if _dependencies is None:
                _dependencies = ApplicationDependencies(
                    vehicles=InMemoryAuthorizedVehicleRepository(),
                    detection_logs=InMemoryDetectionLogRepository(),
                    recognition_activity=InMemoryRecognitionActivityRepository(),
                    evidence_storage=InMemoryEvidenceStorage(),
                )
    return _dependencies
