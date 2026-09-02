from __future__ import annotations

from pathlib import Path

from app.config import normalize_database_url

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_copies_runtime_assets() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY app ./app" in text
    assert "COPY templates ./templates" in text
    assert "COPY static ./static" in text
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
