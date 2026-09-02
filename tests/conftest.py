from __future__ import annotations

import os
from pathlib import Path

_TEST_DB = Path(__file__).resolve().parent / "_pytest.db"
if _TEST_DB.exists():
    try:
        _TEST_DB.unlink()
    except OSError:
        pass

os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"
os.environ["SECRET_KEY"] = "pytest-secret-key"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import User
from app.services.db_migrate import ensure_schema
from app.services.seed import seed_defaults

Base.metadata.create_all(bind=engine)
ensure_schema()
_db = SessionLocal()
try:
    seed_defaults(_db)
finally:
    _db.close()


@pytest.fixture(scope="session")
def raw_client():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client(raw_client: TestClient):
    raw_client.cookies.clear()
    yield raw_client
    raw_client.cookies.clear()


def reset_locales() -> None:
    db = SessionLocal()
    try:
        for user in db.scalars(select(User)):
            user.locale = "ru"
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _reset_user_locales():
    reset_locales()
    yield
    reset_locales()
