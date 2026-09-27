"""Runtime configuration for NagarNetra.

Every knob is env-overridable so the same code runs on a judge's laptop with no
network and no API keys, and on a machine with a live LLM provider.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = BACKEND_DIR.parent
DATA_DIR = ROOT_DIR / "data"
UPLOAD_DIR = BACKEND_DIR / "var" / "uploads"
MODEL_DIR = BACKEND_DIR / "var" / "models"
VAR_DIR = BACKEND_DIR / "var"


class Settings(BaseSettings):
    """Application settings, read from environment or the repo-root .env file."""

    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- identity -------------------------------------------------------
    app_name: str = "NagarNetra"
    challenge_id: str = "PS-18"
    city_name: str = "Pune"
    environment: str = "development"

    # --- security -------------------------------------------------------
    secret_key: str = "nagarnetra-dev-secret-change-me"
    token_ttl_hours: int = 12

    # --- storage --------------------------------------------------------
    database_url: str = ""
    upload_dir: str = ""
    model_dir: str = ""

    # --- LLM ------------------------------------------------------------
    llm_provider: str = "none"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 20.0
    llm_max_tokens: int = 1024

    # --- geocoding ------------------------------------------------------
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    nominatim_user_agent: str = "NagarNetra/1.0 (hackathon prototype; contact: team@nagarnetra.local)"
    nominatim_timeout_seconds: float = 8.0
    geocoding_enabled: bool = True

    # Pune bounding box: (min_lon, min_lat, max_lon, max_lat)
    city_bbox_min_lon: float = 73.7000
    city_bbox_min_lat: float = 18.4000
    city_bbox_max_lon: float = 73.9800
    city_bbox_max_lat: float = 18.6600

    # --- email / SMTP -------------------------------------------------------
    smtp_enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_name: str = "NagarNetra Citizen Portal"
    smtp_from_email: str = "noreply@nagarnetra.local"

    # --- behaviour ------------------------------------------------------
    demo_mode: bool = True
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173"
    max_upload_mb: int = 8
    process_inline: bool = False

    @field_validator("llm_provider")
    @classmethod
    def _normalise_provider(cls, value: str) -> str:
        allowed = {"none", "anthropic", "gemini", "openai"}
        cleaned = (value or "none").strip().lower()
        if cleaned not in allowed:
            raise ValueError(f"LLM_PROVIDER must be one of {sorted(allowed)}, got {value!r}")
        return cleaned

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        VAR_DIR.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(VAR_DIR / 'nagarnetra.db').as_posix()}"

    @property
    def resolved_upload_dir(self) -> Path:
        path = Path(self.upload_dir) if self.upload_dir else UPLOAD_DIR
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def resolved_model_dir(self) -> Path:
        path = Path(self.model_dir) if self.model_dir else MODEL_DIR
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def city_bbox(self) -> tuple[float, float, float, float]:
        return (
            self.city_bbox_min_lon,
            self.city_bbox_min_lat,
            self.city_bbox_max_lon,
            self.city_bbox_max_lat,
        )

    @property
    def llm_active(self) -> bool:
        """True only when a provider is selected *and* its credential exists."""
        if self.llm_provider == "none":
            return False
        key = {
            "anthropic": self.anthropic_api_key,
            "gemini": self.gemini_api_key,
            "openai": self.openai_api_key,
        }.get(self.llm_provider)
        return bool(key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
