"""Health route."""

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["system"])


@router.get("/health", summary="Check backend availability")
@router.get("/api/health", include_in_schema=False)
async def health() -> dict[str, str]:
    """Return deterministic process health without external dependencies."""

    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.service_name,
        "version": settings.app_version,
    }
