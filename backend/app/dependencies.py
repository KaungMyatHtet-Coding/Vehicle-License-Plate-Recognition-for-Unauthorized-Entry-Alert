"""Shared process-local application dependencies with Supabase database support."""

from dataclasses import dataclass
import logging
import threading

from supabase import create_client

from app.core.config import get_settings
from app.repositories.contracts import (
    AuthorizedVehicleRepository,
    DetectionLogRepository,
    RecognitionActivityRepository,
)
from app.repositories.memory import (
    InMemoryAuthorizedVehicleRepository,
    InMemoryDetectionLogRepository,
    InMemoryRecognitionActivityRepository,
)
from app.repositories.supabase_repo import (
    SupabaseAuthorizedVehicleRepository,
    SupabaseDetectionLogRepository,
)
from app.services.evidence_storage import InMemoryEvidenceStorage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApplicationDependencies:
    vehicles: AuthorizedVehicleRepository
    detection_logs: DetectionLogRepository
    recognition_activity: RecognitionActivityRepository
    evidence_storage: InMemoryEvidenceStorage


_dependencies: ApplicationDependencies | None = None
_lock = threading.Lock()


def get_application_dependencies() -> ApplicationDependencies:
    global _dependencies
    if _dependencies is None:
        with _lock:
            if _dependencies is None:
                settings = get_settings()

                if settings.supabase_url and settings.supabase_service_role_key:
                    try:
                        logger.info("Initializing Supabase database client...")
                        client = create_client(
                            settings.supabase_url, settings.supabase_service_role_key
                        )
                        vehicles_repo = SupabaseAuthorizedVehicleRepository(client)
                        detection_logs_repo = SupabaseDetectionLogRepository(client)
                        logger.info("Successfully connected to Supabase Live Database!")
                    except Exception as exc:
                        logger.warning(
                            "Failed to connect to Supabase (%s); falling back to InMemory repositories.",
                            exc,
                        )
                        vehicles_repo = InMemoryAuthorizedVehicleRepository()
                        detection_logs_repo = InMemoryDetectionLogRepository()
                else:
                    logger.info(
                        "No Supabase credentials found; using InMemory repositories."
                    )
                    vehicles_repo = InMemoryAuthorizedVehicleRepository()
                    detection_logs_repo = InMemoryDetectionLogRepository()

                _dependencies = ApplicationDependencies(
                    vehicles=vehicles_repo,
                    detection_logs=detection_logs_repo,
                    recognition_activity=InMemoryRecognitionActivityRepository(),
                    evidence_storage=InMemoryEvidenceStorage(),
                )
    return _dependencies
