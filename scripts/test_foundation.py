"""Foundation checks: i18n + DATABASE_URL normalize. No pytest required."""
from __future__ import annotations

from app.config import normalize_database_url
from app.i18n import translate
from app.models import CashEntry, OrderStatus, UserRole


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


def test_enums() -> None:
    assert UserRole.accountant.value == "accountant"
    assert OrderStatus.in_progress.value == "in_progress"
    assert OrderStatus.issued.value == "issued"
    assert CashEntry.__tablename__ == "cash_entries"


if __name__ == "__main__":
    test_normalize_database_url()
    test_i18n()
    test_enums()
    print("foundation ok")
