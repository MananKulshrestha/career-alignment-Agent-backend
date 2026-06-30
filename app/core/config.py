from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Career Alignment Agent Backend"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    backend_cors_origins: list[AnyHttpUrl | str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    database_url: str = "sqlite:///./job_assistance_dev.db"
    create_db_on_startup: bool = True

    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None

    enable_llm: bool = False
    openai_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    cheap_model: str = "openai:gpt-5.2"
    reliable_model: str = "openai:gpt-5.2"
    writing_model: str = "openai:gpt-5.2"
    max_model_retries: int = Field(default=2, ge=0, le=5)

    http_timeout_seconds: int = Field(default=15, ge=1, le=60)
    max_job_text_chars: int = Field(default=50_000, ge=5_000, le=200_000)
    job_search_api_url: str | None = None
    job_search_api_key: SecretStr | None = None

    artifacts_dir: Path = Path("./artifacts")
    latex_engine: str = "pdflatex"
    latex_compile_timeout_seconds: int = Field(default=20, ge=5, le=120)

    @field_validator("backend_cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> Any:
        if isinstance(value, str) and value and not value.startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def llm_ready(self) -> bool:
        return self.enable_llm and (self.openai_api_key is not None or self.gemini_api_key is not None)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
