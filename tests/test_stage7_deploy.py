from __future__ import annotations

from pathlib import Path

import pytest

from app.config import (
    DEFAULT_SECRET_KEY,
    LOCAL_DATABASE_URL,
    Settings,
    get_settings,
    normalize_database_url,
    resolve_database_url,
    validate_production_settings,
)
from tests.helpers import login

ROOT = Path(__file__).resolve().parents[1]
STRONG_KEY = "x" * 48
SEED_USERS = "admin:admin::Admin|mech_test:mechanic:batumi:Mech"


def test_prod_compose_uses_pg_core_and_ghcr() -> None:
    text = (ROOT / "deploy" / "docker-compose.prod.yml").read_text(encoding="utf-8")
    assert "image: ghcr.io/ivanbondarenkoit/service-center-erp:${IMAGE_TAG:-main}" in text
    assert "container_name: service-center-erp" in text
    assert '"127.0.0.1:8090:8080"' in text
    assert "/health" in text
    assert "TZ: Asia/Tbilisi" in text
    assert "build:" not in text
    assert "  db:" not in text
    assert "postgres" not in text.lower()
    assert "volumes:" not in text
    assert "scerp_prod_pgdata" not in text
    networks = text.split("\nnetworks:", 1)[1]
    assert "pgnet:\n    external: true" in networks
    assert "edge:\n    external: true" in networks


def test_dockerfile_trusts_proxy_headers() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "--proxy-headers" in text
    assert "--forwarded-allow-ips='*'" in text


def test_ci_cd_workflow_builds_ghcr_image() -> None:
    text = (ROOT / ".github" / "workflows" / "ci-cd.yml").read_text(encoding="utf-8")
    assert "pytest -q" in text
    assert "scripts/check_pg_schema.py" in text
    assert "ghcr.io/ivanbondarenkoit/service-center-erp" in text
    assert "type=raw,value=main" in text
    assert "type=sha,prefix=sha-" in text
    assert "refs/heads/main" in text


def _settings(**kw) -> Settings:
    base = {
        "app_env": "production",
        "secret_key": STRONG_KEY,
        "seed_users": SEED_USERS,
        "seed_admin_password": "Adm1n-strong-pass",
        "seed_mechanic_password": "Mech-strong-pass",
        "seed_accountant_password": "Acc-strong-pass",
    }
    base.update(kw)
    return Settings(**base)


def test_production_guard_rejects_default_secret(monkeypatch) -> None:
    monkeypatch.delenv("SEED_PASSWORD_ADMIN", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_production_settings(_settings(secret_key=DEFAULT_SECRET_KEY))
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_production_settings(_settings(secret_key="short"))


def test_production_guard_rejects_default_seed_passwords(monkeypatch) -> None:
    monkeypatch.delenv("SEED_PASSWORD_ADMIN", raising=False)
    monkeypatch.delenv("SEED_PASSWORD_MECH_TEST", raising=False)
    with pytest.raises(RuntimeError, match="mech_test"):
        validate_production_settings(_settings(seed_mechanic_password="mechanic123"))
    monkeypatch.setenv("SEED_PASSWORD_MECH_TEST", "per-user-strong")
    validate_production_settings(_settings(seed_mechanic_password="mechanic123"))


def test_production_guard_passes_and_skips_in_dev(monkeypatch) -> None:
    monkeypatch.delenv("SEED_PASSWORD_ADMIN", raising=False)
    monkeypatch.delenv("SEED_PASSWORD_MECH_TEST", raising=False)
    validate_production_settings(_settings())
    validate_production_settings(
        _settings(app_env="development", secret_key=DEFAULT_SECRET_KEY, seed_admin_password="admin123")
    )


def test_session_cookie_secure_flag(client, monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "session_cookie_secure", True)
    r = login(client, "admin", settings.seed_admin_password)
    assert r.status_code == 303
    cookies = r.headers.get_list("set-cookie")
    session = [c for c in cookies if c.startswith(settings.session_cookie_name + "=")]
    assert session and "secure" in session[0].lower()
    assert all("secure" in c.lower() for c in cookies)
    monkeypatch.setattr(settings, "session_cookie_secure", False)
    r2 = login(client, "admin", settings.seed_admin_password)
    assert all("secure" not in c.lower() for c in r2.headers.get_list("set-cookie"))


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
