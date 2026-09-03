from __future__ import annotations

from pathlib import Path

import pytest

from app.config import LOCAL_DATABASE_URL, normalize_database_url, resolve_database_url

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_copies_runtime_assets() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY app ./app" in text
    assert "COPY templates ./templates" in text
    assert "COPY static ./static" in text
    assert "${PORT:-8080}" in text
    assert "EXPOSE 8080" in text
    assert '"--port", "8035"' not in text
    assert (ROOT / "app" / "i18n" / "ru.json").is_file()
    assert (ROOT / "app" / "i18n" / "en.json").is_file()
    assert (ROOT / "app" / "i18n" / "ka.json").is_file()


def test_railway_toml_is_web_not_cron() -> None:
    text = (ROOT / "railway.toml").read_text(encoding="utf-8")
    assert "$PORT" in text
    assert "cronSchedule" not in text
    assert "healthcheckPath" in text
    assert "/health" in text


def test_gitignore_keeps_secrets_out() -> None:
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in text
    assert "data/input/*.xlsx" in text


def test_normalize_database_url_railway() -> None:
    assert (
        normalize_database_url("postgres://u:p@h:5432/db")
        == "postgresql+psycopg2://u:p@h:5432/db"
    )
    assert (
        normalize_database_url("postgresql://u:p@h:5432/db")
        == "postgresql+psycopg2://u:p@h:5432/db"
    )


def test_resolve_uses_private_url_when_database_url_is_localhost(monkeypatch) -> None:
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    monkeypatch.delenv("RAILWAY_SERVICE_ID", raising=False)
    monkeypatch.setenv("DATABASE_URL", LOCAL_DATABASE_URL)
    monkeypatch.setenv(
        "DATABASE_PRIVATE_URL",
        "postgres://u:p@postgres.railway.internal:5432/railway",
    )
    assert (
        resolve_database_url(LOCAL_DATABASE_URL)
        == "postgresql+psycopg2://u:p@postgres.railway.internal:5432/railway"
    )


def test_resolve_uses_pghost_when_urls_missing(monkeypatch) -> None:
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    monkeypatch.delenv("RAILWAY_SERVICE_ID", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_PRIVATE_URL", raising=False)
    monkeypatch.delenv("DATABASE_PUBLIC_URL", raising=False)
    monkeypatch.setenv("PGHOST", "postgres.railway.internal")
    monkeypatch.setenv("PGUSER", "postgres")
    monkeypatch.setenv("PGPASSWORD", "s3cret")
    monkeypatch.setenv("PGPORT", "5432")
    monkeypatch.setenv("PGDATABASE", "railway")
    assert (
        resolve_database_url(None)
        == "postgresql+psycopg2://postgres:s3cret@postgres.railway.internal:5432/railway"
    )


def test_resolve_keeps_sqlite(monkeypatch) -> None:
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    sqlite = "sqlite:///./scerp_local.db"
    monkeypatch.setenv("DATABASE_URL", sqlite)
    assert resolve_database_url(sqlite) == sqlite


def test_resolve_treats_empty_database_url_as_missing(monkeypatch) -> None:
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("RAILWAY_PROJECT_ID", raising=False)
    monkeypatch.delenv("RAILWAY_SERVICE_ID", raising=False)
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv(
        "DATABASE_PUBLIC_URL",
        "postgres://u:p@postgres.railway.internal:5432/railway",
    )
    assert (
        resolve_database_url("")
        == "postgresql+psycopg2://u:p@postgres.railway.internal:5432/railway"
    )


def test_resolve_fails_on_railway_without_postgres(monkeypatch) -> None:
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_PRIVATE_URL", raising=False)
    monkeypatch.delenv("DATABASE_PUBLIC_URL", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        resolve_database_url(LOCAL_DATABASE_URL)
