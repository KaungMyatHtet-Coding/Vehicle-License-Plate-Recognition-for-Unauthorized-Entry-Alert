"""FastAPI application entry point for the backend foundation."""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette import status
from starlette.exceptions import HTTPException

from app.api.routes.health import router as health_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.project_title,
    version=settings.app_version,
    description="Backend foundation for Vehicle License Plate Recognition for Unauthorized Entry Alert.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Accept", "Content-Type"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_, exc: RequestValidationError) -> JSONResponse:
    """Return a stable validation envelope without exposing internals."""

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "The request did not pass validation.",
                "fields": [error.get("loc", []) for error in exc.errors()],
            }
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException) -> JSONResponse:
    """Return a stable error envelope without exposing server internals."""

    message = (
        exc.detail
        if isinstance(exc.detail, str)
        else "The request could not be completed."
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "HTTP_ERROR", "message": message}},
        headers=exc.headers,
    )


@app.get("/", tags=["system"])
async def api_information() -> dict[str, str]:
    """Return public API information and links to the documentation."""

    return {
        "title": settings.project_title,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
    }


app.include_router(health_router)
