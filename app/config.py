from __future__ import annotations

import os
from functools import lru_cache
from urllib.parse import quote_plus, unquote, urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_DATABASE_URL = "postgresql+psycopg2://scerp:scerp@localhost:5433/service_center_erp"

_RAILWAY_MISSING_DB = (
    "DATABASE_URL is localhost or unset. Railway Postgres is not linked to this web service. "
    "In Railway: add a PostgreSQL database in the same project, open this service → Variables → "
    "add a reference DATABASE_URL=${{Postgres.DATABASE_URL}} "
    "then redeploy. Do not copy a local localhost:5433 URL into Railway variables."
)


def normalize_database_url(url: str) -> str:
    """Railway/Heroku give postgres://; SQLAlchemy needs postgresql+psycopg2://."""
    raw = (url or "").strip()
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://") :]
    scheme, sep, rest = raw.partition("://")
    if sep and scheme == "postgresql":
        return f"postgresql+psycopg2://{rest}"
    return raw


def database_url_host(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"postgresql://{raw}")
    return unquote(parsed.hostname or "")


def _is_loopback_db_url(url: str) -> bool:
    raw = (url or "").strip().lower()
    if raw.startswith("sqlite"):
        return False
    host = database_url_host(url).lower()
    return host in {"", "localhost", "127.0.0.1", "::1"}


def _on_railway() -> bool:
    return bool(
        os.environ.get("RAILWAY_ENVIRONMENT")
        or os.environ.get("RAILWAY_PROJECT_ID")
        or os.environ.get("RAILWAY_SERVICE_ID")
    )


def _url_from_pg_env() -> str:
    host = (os.environ.get("PGHOST") or "").strip()
    if not host:
        return ""
    user = (os.environ.get("PGUSER") or "postgres").strip() or "postgres"
    password = os.environ.get("PGPASSWORD") or ""
    port = (os.environ.get("PGPORT") or "5432").strip() or "5432"
    dbname = (os.environ.get("PGDATABASE") or "railway").strip() or "railway"
    auth = f"{quote_plus(user)}:{quote_plus(password)}" if password else quote_plus(user)
    return f"postgresql://{auth}@{host}:{port}/{dbname}"


def resolve_database_url(value: str | None = None) -> str:
    """Prefer a real Postgres URL; Railway often exposes PRIVATE/PUBLIC/PG* instead of DATABASE_URL."""
    chosen = (value or "").strip()
    if not chosen or _is_loopback_db_url(chosen):
        for key in ("DATABASE_URL", "DATABASE_PRIVATE_URL", "DATABASE_PUBLIC_URL"):
            alt = (os.environ.get(key) or "").strip()
            if alt and not _is_loopback_db_url(alt):
                chosen = alt
                break
        if not chosen or _is_loopback_db_url(chosen):
            from_pg = _url_from_pg_env()
            if from_pg and not _is_loopback_db_url(from_pg):
                chosen = from_pg
        if not chosen:
            chosen = LOCAL_DATABASE_URL
    chosen = normalize_database_url(chosen)
    if _on_railway() and _is_loopback_db_url(chosen):
        raise RuntimeError(_RAILWAY_MISSING_DB)
    return chosen


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )

    app_name: str = "Service Center ERP"
    secret_key: str = "change-me-in-production"
    database_url: str = LOCAL_DATABASE_URL
    session_cookie_name: str = "scerp_session"
    session_max_age: int = 60 * 60 * 12

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_db_url(cls, value: str) -> str:
        return resolve_database_url(value if isinstance(value, str) else None)

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
