"""Environment-based settings for the backend foundation."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    """Safe development settings; external services are not required."""

    model_config = SettingsConfigDict(
        env_file=("backend/.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    project_title: str = Field(
        default="Vehicle License Plate Recognition for Unauthorized Entry Alert",
        validation_alias="PROJECT_TITLE",
    )
    service_name: str = Field(
        default="vehicle-license-backend", validation_alias="SERVICE_NAME"
    )
    app_version: str = Field(default="0.1.0", validation_alias="APP_VERSION")
    app_env: str = Field(default="development", validation_alias="APP_ENV")
    app_host: str = Field(default="127.0.0.1", validation_alias="APP_HOST")
    app_port: int = Field(default=8000, validation_alias="APP_PORT")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    max_image_bytes: int = Field(
        default=10 * 1024 * 1024, validation_alias="MAX_IMAGE_BYTES"
    )
    min_image_width: int = Field(default=32, validation_alias="MIN_IMAGE_WIDTH")
    min_image_height: int = Field(default=32, validation_alias="MIN_IMAGE_HEIGHT")
    max_image_width: int = Field(default=10_000, validation_alias="MAX_IMAGE_WIDTH")
    max_image_height: int = Field(default=10_000, validation_alias="MAX_IMAGE_HEIGHT")
    max_image_pixels: int = Field(
        default=25_000_000, validation_alias="MAX_IMAGE_PIXELS"
    )
    detector_model_path: Path | None = Field(
        default=None, validation_alias="DETECTOR_MODEL_PATH"
    )
    detector_confidence_threshold: float = Field(
        default=0.25, ge=0.0, le=1.0, validation_alias="DETECTOR_CONFIDENCE_THRESHOLD"
    )
    detector_nms_iou_threshold: float = Field(
        default=0.45, ge=0.0, le=1.0, validation_alias="DETECTOR_NMS_IOU_THRESHOLD"
    )
    ocr_min_confidence: float = Field(
        default=0.80, ge=0.0, le=1.0, validation_alias="OCR_MIN_CONFIDENCE"
    )
    ocr_full_pipeline_fallback: bool = Field(
        default=True, validation_alias="OCR_FULL_PIPELINE_FALLBACK"
    )
    decision_min_confidence: float = Field(
        default=0.80, ge=0.0, le=1.0, validation_alias="DECISION_MIN_CONFIDENCE"
    )
    frontend_origins: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:3000"], validation_alias="FRONTEND_ORIGINS"
    )

    @field_validator("decision_min_confidence", mode="before")
    @classmethod
    def reject_boolean_decision_threshold(cls, value: object) -> object:
        """Reject bool before Pydantic can coerce it to zero or one."""

        if isinstance(value, bool):
            raise ValueError("DECISION_MIN_CONFIDENCE must be numeric")
        return value

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def parse_frontend_origins(cls, value: str | list[str]) -> list[str]:
        """Accept a comma-separated development value from a local .env file."""

        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return one cached settings object for the process."""

    return Settings()
