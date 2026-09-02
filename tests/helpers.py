from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import User

settings = get_settings()


def login(client: TestClient, login_name: str, password: str):
    return client.post(
        "/login",
        data={"login": login_name, "password": password},
        follow_redirects=False,
    )


def user_ids(login_name: str) -> tuple[int, int | None]:
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.login == login_name))
        assert user is not None
        return user.id, user.service_center_id
    finally:
        db.close()

