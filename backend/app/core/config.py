"""Environment-based settings for the backend foundation."""

from functools import lru_cache
import os
import re
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    """Safe development settings; external services are not required."""

    model_config = SettingsConfigDict(
        env_file=(
            None
            if os.environ.get("CVPX_DISABLE_DOTENV") == "1"
            else ("backend/.env", ".env")
        ),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_mode: Literal["localhost", "production"] = Field(
        default="localhost", validation_alias="APP_MODE"
    )
    repository_mode: Literal["memory", "supabase"] = Field(
        default="memory", validation_alias="REPOSITORY_MODE"
    )
    enable_experimental_video: bool = Field(
        default=False, validation_alias="ENABLE_EXPERIMENTAL_VIDEO"
    )

    supabase_url: str | None = Field(default=None, validation_alias="SUPABASE_URL")
    supabase_service_role_key: str | None = Field(
        default=None, validation_alias="SUPABASE_SERVICE_ROLE_KEY"
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
    max_recognition_candidates: int = Field(
        default=3,
        ge=1,
        le=5,
        validation_alias="MAX_RECOGNITION_CANDIDATES",
    )
    supported_plate_regions: Annotated[list[str], NoDecode] = Field(
        default=["YGN", "MDY", "NPT"], validation_alias="SUPPORTED_PLATE_REGIONS"
    )
    min_plate_length: int = Field(
        default=7, ge=4, le=20, validation_alias="MIN_PLATE_LENGTH"
    )
    max_plate_length: int = Field(
        default=12, ge=4, le=20, validation_alias="MAX_PLATE_LENGTH"
    )
    candidate_ambiguity_margin: float = Field(
        default=0.08,
        ge=0.0,
        le=0.5,
        validation_alias="CANDIDATE_AMBIGUITY_MARGIN",
    )
    video_allowed_extensions: Annotated[list[str], NoDecode] = Field(
        default=[".mp4", ".avi", ".mov"], validation_alias="VIDEO_ALLOWED_EXTENSIONS"
    )
    video_max_upload_bytes: int = Field(
        default=25 * 1024 * 1024,
        ge=1,
        le=50 * 1024 * 1024,
        validation_alias="VIDEO_MAX_UPLOAD_BYTES",
    )
    video_max_duration_seconds: float = Field(
        default=10.0,
        gt=0.0,
        le=60.0,
        validation_alias="VIDEO_MAX_DURATION_SECONDS",
    )
    video_target_fps: float = Field(
        default=2.0, gt=0.0, le=10.0, validation_alias="VIDEO_TARGET_FPS"
    )
    video_max_decoded_frames: int = Field(
        default=300, ge=1, le=2000, validation_alias="VIDEO_MAX_DECODED_FRAMES"
    )
    video_max_sampled_frames: int = Field(
        default=20, ge=1, le=100, validation_alias="VIDEO_MAX_SAMPLED_FRAMES"
    )
    video_max_frame_width: int = Field(
        default=1920, ge=32, le=10_000, validation_alias="VIDEO_MAX_FRAME_WIDTH"
    )
    video_max_frame_height: int = Field(
        default=1080, ge=32, le=10_000, validation_alias="VIDEO_MAX_FRAME_HEIGHT"
    )
    video_max_frame_pixels: int = Field(
        default=2_073_600,
        ge=1024,
        le=25_000_000,
        validation_alias="VIDEO_MAX_FRAME_PIXELS",
    )
    video_consensus_min_observations: int = Field(
        default=2,
        ge=2,
        le=20,
        validation_alias="VIDEO_CONSENSUS_MIN_OBSERVATIONS",
    )
    video_consensus_window_frames: int = Field(
        default=8,
        ge=2,
        le=20,
        validation_alias="VIDEO_CONSENSUS_WINDOW_FRAMES",
    )
    decision_min_confidence: float = Field(
        default=0.80, ge=0.0, le=1.0, validation_alias="DECISION_MIN_CONFIDENCE"
    )
    evidence_storage_bucket: str = Field(
        default="detection-evidence",
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9._-]{0,99}$",
        validation_alias="EVIDENCE_STORAGE_BUCKET",
    )
    evidence_signed_access_ttl_seconds: int = Field(
        default=300,
        ge=60,
        le=3600,
        validation_alias="EVIDENCE_SIGNED_ACCESS_TTL_SECONDS",
    )
    evidence_retention_days: int = Field(
        default=30,
        ge=1,
        le=365,
        validation_alias="EVIDENCE_RETENTION_DAYS",
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

    @field_validator(
        "evidence_signed_access_ttl_seconds",
        "evidence_retention_days",
        mode="before",
    )
    @classmethod
    def reject_boolean_evidence_limits(cls, value: object) -> object:
        """Reject bool before Pydantic can coerce it to an integer."""

        if isinstance(value, bool):
            raise ValueError("Evidence limits must be integers")
        return value

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def parse_frontend_origins(cls, value: str | list[str]) -> list[str]:
        """Accept a comma-separated development value from a local .env file."""

        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("supported_plate_regions", mode="before")
    @classmethod
    def parse_supported_plate_regions(cls, value: str | list[str]) -> list[str]:
        """Accept bounded comma-separated region prefixes without secrets."""

        values = (
            [item.strip() for item in value.split(",") if item.strip()]
            if isinstance(value, str)
            else value
        )
        if not isinstance(values, list) or not values:
            raise ValueError("SUPPORTED_PLATE_REGIONS must contain prefixes")
        normalized = [str(item).upper() for item in values]
        if any(not re.fullmatch(r"[A-Z]{2,8}", item) for item in normalized):
            raise ValueError("SUPPORTED_PLATE_REGIONS contains an invalid prefix")
        return normalized

    @field_validator("video_allowed_extensions", mode="before")
    @classmethod
    def parse_video_extensions(cls, value: str | list[str]) -> list[str]:
        """Accept only a bounded list of lowercase dotted video extensions."""

        values = (
            [item.strip().lower() for item in value.split(",") if item.strip()]
            if isinstance(value, str)
            else value
        )
        if not isinstance(values, list) or not values:
            raise ValueError("VIDEO_ALLOWED_EXTENSIONS must contain extensions")
        normalized = [str(item).lower() for item in values]
        supported = {".mp4", ".avi", ".mov"}
        if any(item not in supported for item in normalized):
            raise ValueError("VIDEO_ALLOWED_EXTENSIONS contains an invalid extension")
        if len(set(normalized)) != len(normalized):
            raise ValueError("VIDEO_ALLOWED_EXTENSIONS must not contain duplicates")
        return normalized

    @model_validator(mode="after")
    def validate_runtime_boundary(self) -> "Settings":
        """Keep the default prototype on loopback and validate explicit adapters."""

        if self.repository_mode == "supabase" and not (
            self.supabase_url and self.supabase_service_role_key
        ):
            raise ValueError("Supabase repository configuration is incomplete.")
        if self.app_mode == "localhost":
            if self.app_host not in {"127.0.0.1", "localhost", "::1"}:
                raise ValueError("Localhost mode requires a loopback application host.")
            if not self.frontend_origins or any(
                not self._is_loopback_origin(origin) for origin in self.frontend_origins
            ):
                raise ValueError("Localhost mode requires loopback frontend origins.")
        if self.min_plate_length > self.max_plate_length:
            raise ValueError("MIN_PLATE_LENGTH cannot exceed MAX_PLATE_LENGTH")
        if self.video_consensus_min_observations > self.video_consensus_window_frames:
            raise ValueError(
                "VIDEO_CONSENSUS_MIN_OBSERVATIONS cannot exceed VIDEO_CONSENSUS_WINDOW_FRAMES"
            )
        if self.video_max_sampled_frames > self.video_max_decoded_frames:
            raise ValueError(
                "VIDEO_MAX_SAMPLED_FRAMES cannot exceed VIDEO_MAX_DECODED_FRAMES"
            )
        if self.video_consensus_window_frames > self.video_max_sampled_frames:
            raise ValueError(
                "VIDEO_CONSENSUS_WINDOW_FRAMES cannot exceed VIDEO_MAX_SAMPLED_FRAMES"
            )
        if (
            self.video_max_frame_width * self.video_max_frame_height
            > self.video_max_frame_pixels
        ):
            raise ValueError(
                "Configured video frame dimensions exceed VIDEO_MAX_FRAME_PIXELS"
            )
        return self

    @staticmethod
    def _is_loopback_origin(origin: str) -> bool:
        try:
            parsed = urlparse(origin)
            return (
                parsed.scheme in {"http", "https"}
                and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
                and parsed.username is None
                and parsed.password is None
                and not parsed.path.rstrip("/")
                and not parsed.params
                and not parsed.query
                and not parsed.fragment
            )
        except ValueError:
            return False


@lru_cache
def get_settings() -> Settings:
    """Return one cached settings object for the process."""

    return Settings()
