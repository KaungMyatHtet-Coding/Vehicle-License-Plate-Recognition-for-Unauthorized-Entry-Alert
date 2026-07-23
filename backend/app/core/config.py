"""Environment-based settings for the backend foundation."""

from functools import lru_cache
from typing import Annotated

from pydantic import Field
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from pydantic import field_validator


class Settings(BaseSettings):
    """Safe development settings; external services are not required."""

    model_config = SettingsConfigDict(
        env_file=".env",
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
    frontend_origins: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:3000"], validation_alias="FRONTEND_ORIGINS"
    )

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
