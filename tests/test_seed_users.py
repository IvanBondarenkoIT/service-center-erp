from __future__ import annotations

from app.config import DEFAULT_SEED_USERS, Settings
from app.models import UserRole
from app.services.seed import parse_seed_users, resolve_seed_password, seed_password_env_key


def test_parse_default_seed_users() -> None:
    specs = parse_seed_users(DEFAULT_SEED_USERS)
    logins = [s.login for s in specs]
    assert logins == [
        "admin",
        "accountant",
        "mechanic_batumi",
        "mechanic_tbilisi1",
        "mechanic_tbilisi2",
    ]
    by_login = {s.login: s for s in specs}
    assert by_login["admin"].role is UserRole.admin
    assert by_login["admin"].center_code is None
    assert by_login["mechanic_batumi"].center_code == "batumi"
    assert by_login["mechanic_tbilisi1"].center_code == "tbilisi"
    assert by_login["mechanic_tbilisi1"].full_name == "Механик Тбилиси 1"
    assert by_login["mechanic_tbilisi2"].center_code == "tbilisi2"


def test_parse_extra_user() -> None:
    extra = DEFAULT_SEED_USERS + "|mechanic_kutaisi:mechanic:kutaisi:Механик Кутаиси"
    specs = parse_seed_users(extra)
    kutaisi = next(s for s in specs if s.login == "mechanic_kutaisi")
    assert kutaisi.role is UserRole.mechanic
    assert kutaisi.center_code == "kutaisi"


def test_per_user_password_env(monkeypatch) -> None:
    settings = Settings(
        seed_admin_password="admin123",
        seed_mechanic_password="mechanic123",
        seed_accountant_password="accountant123",
    )
    monkeypatch.setenv(seed_password_env_key("mechanic_batumi"), "batumi-secret")
    assert (
        resolve_seed_password("mechanic_batumi", UserRole.mechanic, settings)
        == "batumi-secret"
    )
    assert (
        resolve_seed_password("mechanic_tbilisi1", UserRole.mechanic, settings)
        == "mechanic123"
    )
    assert resolve_seed_password("admin", UserRole.admin, settings) == "admin123"
