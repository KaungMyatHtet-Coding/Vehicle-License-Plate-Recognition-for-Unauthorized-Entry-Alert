"""Explicit, deterministic application dependency construction."""

from dataclasses import dataclass
import logging
import threading
from collections.abc import Callable
from typing import Any

from supabase import create_client

from app.core.config import Settings, get_settings
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


def build_application_dependencies(
    settings: Settings,
    *,
    supabase_client_factory: Callable[[str, str], Any] = create_client,
) -> ApplicationDependencies:
    """Build one coherent adapter set without implicit fallback behavior."""

    if settings.repository_mode == "memory":
        return ApplicationDependencies(
            vehicles=InMemoryAuthorizedVehicleRepository(),
            detection_logs=InMemoryDetectionLogRepository(),
            recognition_activity=InMemoryRecognitionActivityRepository(),
            evidence_storage=InMemoryEvidenceStorage(),
        )

    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("Supabase repository configuration is incomplete.")
    try:
        client = supabase_client_factory(
            settings.supabase_url, settings.supabase_service_role_key
        )
    except Exception:
        raise RuntimeError("Supabase repository initialization failed.") from None
    return ApplicationDependencies(
        vehicles=SupabaseAuthorizedVehicleRepository(client),
        detection_logs=SupabaseDetectionLogRepository(client),
        recognition_activity=InMemoryRecognitionActivityRepository(),
        evidence_storage=InMemoryEvidenceStorage(),
    )


def reset_application_dependencies() -> None:
    """Clear the supported process cache for tests and controlled reconfiguration."""

    global _dependencies
    with _lock:
        _dependencies = None


def get_application_dependencies() -> ApplicationDependencies:
    """Return a shared dependency set selected by explicit repository mode."""

    global _dependencies
    if _dependencies is None:
        with _lock:
            if _dependencies is None:
                settings = get_settings()
                logger.info("Initializing %s repositories.", settings.repository_mode)
                _dependencies = build_application_dependencies(settings)
    return _dependencies
