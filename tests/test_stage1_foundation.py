from __future__ import annotations

from sqlalchemy import inspect, select

from app.config import get_settings, normalize_database_url
from app.database import SessionLocal, engine
from app.i18n import translate
from app.models import CashEntry, CashOpening, OrderStatus, User, UserRole
from tests.helpers import login, settings


def test_normalize_database_url() -> None:
    assert (
        normalize_database_url("postgres://u:p@h:5432/db")
        == "postgresql+psycopg2://u:p@h:5432/db"
    )
    assert (
        normalize_database_url("postgresql://u:p@h:5432/db")
        == "postgresql+psycopg2://u:p@h:5432/db"
    )
    already = "postgresql+psycopg2://u:p@h:5432/db"
    assert normalize_database_url(already) == already
    assert normalize_database_url("sqlite:///./scerp_local.db") == "sqlite:///./scerp_local.db"


def test_i18n() -> None:
    assert translate("nav.orders", "ru") == "Заказы"
    assert translate("nav.orders", "en") == "Orders"
    assert translate("auth.bad_credentials", "ka")
    assert translate("missing.key", "en") == "missing.key"
    assert translate("nav.orders", "xx") == "Заказы"


def test_enums_and_tables() -> None:
    assert UserRole.accountant.value == "accountant"
    assert OrderStatus.in_progress.value == "in_progress"
    assert OrderStatus.issued.value == "issued"
    assert CashEntry.__tablename__ == "cash_entries"
    assert CashOpening.__tablename__ == "cash_openings"
    names = inspect(engine).get_table_names()
    assert "cash_entries" in names
    assert "cash_openings" in names
    assert "users" in names
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    assert "locale" in cols
    cols_orders = {c["name"] for c in inspect(engine).get_columns("service_orders")}
    assert "status" in cols_orders


def test_seed_accountant() -> None:
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.login == "accountant"))
        assert user is not None
        assert user.role == UserRole.accountant
        assert user.locale == "ru"
    finally:
        db.close()


def test_health(client) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_login_default_ru(client) -> None:
    r = client.get("/login")
    assert r.status_code == 200
    assert 'lang="ru"' in r.text
    assert get_settings().app_name in r.text or "Войти" in r.text


def test_login_cookie_en(client) -> None:
    client.cookies.set("scerp_locale", "en")
    r = client.get("/login")
    assert r.status_code == 200
    assert "Sign in" in r.text


def test_bad_password_translated(client) -> None:
    r = client.post(
        "/login",
        data={"login": "admin", "password": "wrong"},
        headers={"Cookie": "scerp_locale=en"},
        follow_redirects=False,
    )
    assert r.status_code == 401
    assert "Invalid login or password" in r.text


def test_admin_login_goes_home(client) -> None:
    r = login(client, "admin", settings.seed_admin_password)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
