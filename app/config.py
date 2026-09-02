from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """Railway/Heroku give postgres://; SQLAlchemy needs postgresql+psycopg2://."""
    raw = (url or "").strip()
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://") :]
    scheme, sep, rest = raw.partition("://")
    if sep and scheme == "postgresql":
        return f"postgresql+psycopg2://{rest}"
    return raw


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Service Center ERP"
    secret_key: str = "change-me-in-production"
    database_url: str = "postgresql+psycopg2://scerp:scerp@localhost:5433/service_center_erp"
    session_cookie_name: str = "scerp_session"
    session_max_age: int = 60 * 60 * 12

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_db_url(cls, value: str) -> str:
        return normalize_database_url(value) if isinstance(value, str) else value

    proxy_api_url: str = ""
    proxy_api_token: str = ""
    proxy_api_timeout: float = 90.0
    proxy_api_max_retries: int = 3

    erp_sync_batch_size: int = 150
    erp_sync_pause_ms: int = 500
    erp_sync_max_batches: int = 20
    erp_sync_stale_hours: int = 24
    erp_sync_refresh_batch: int = 100
    erp_sync_probe_skip_hours: int = 6

    seed_admin_password: str = "admin123"
    seed_mechanic_password: str = "mechanic123"
    seed_accountant_password: str = "accountant123"

    # Placeholder serial prefix for Excel rows without machine serial
    import_placeholder_serial_prefix: str = "NEED-SERIAL-"


@lru_cache
def get_settings() -> Settings:
    return Settings()
