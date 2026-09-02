from __future__ import annotations

from sqlalchemy import select

from app.database import SessionLocal
from app.i18n import catalog_key_set
from app.models import User
from tests.helpers import login, settings


def test_login_html_shell(client) -> None:
    r = client.get("/login")
    assert r.status_code == 200
    html = r.text
    assert 'lang="' in html
    assert "/static/app.css" in html
    assert "cdn.tailwindcss.com" not in html


def test_post_locale_sets_cookie(client) -> None:
    r = client.post(
        "/locale",
        data={"locale": "en", "next": "/login"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
    assert client.cookies.get("scerp_locale") == "en"
    page = client.get("/login")
    assert "Sign in" in page.text


def test_locale_updates_logged_in_user(client) -> None:
    login(client, "admin", settings.seed_admin_password)
    r = client.post(
        "/locale",
        data={"locale": "ka", "next": "/"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert client.cookies.get("scerp_locale") == "ka"
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.login == "admin"))
        assert user is not None
        assert user.locale == "ka"
    finally:
        db.close()


def test_mechanic_tabs_without_admin_links(client) -> None:
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    assert "Заказы" in html
    assert "Новый" in html
    assert "Касса" in html
    assert 'class="bottom-nav"' in html
    assert "/dict/clients" not in html
    assert "/reports" not in html


def test_admin_has_reports_and_dicts(client) -> None:
    login(client, "admin", settings.seed_admin_password)
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    assert "/reports" in html
    assert "/dict/clients" in html
    assert "/dict/machines" in html
    assert 'class="sidebar"' in html
    assert "/more" in html


def test_accountant_login_and_blocked_orders(client) -> None:
    r = login(client, "accountant", settings.seed_accountant_password)
    assert r.status_code == 303
    assert r.headers["location"] == "/cash"

    home = client.get("/", follow_redirects=False)
    assert home.status_code == 303
    assert home.headers["location"] == "/cash"

    new_order = client.get("/orders/new", follow_redirects=False)
    assert new_order.status_code == 303
    assert new_order.headers["location"] == "/cash"

    cash = client.get("/cash")
    assert cash.status_code == 200
    assert "serial_number" not in cash.text
    assert "/dict/clients" not in cash.text
    assert 'class="bottom-nav"' not in cash.text


def test_screens_use_stitch_css_not_tailwind(client) -> None:
    login(client, "admin", settings.seed_admin_password)
    paths = (
        "/",
        "/orders/new",
        "/cash",
        "/cash/entries",
        "/reports",
        "/dict/clients",
        "/dict/machines",
        "/dict/reasons",
        "/dict/erp-catalog",
        "/more",
    )
    for path in paths:
        page = client.get(path)
        assert page.status_code == 200, path
        html = page.text
        assert "/static/app.css" in html, path
        assert "cdn.tailwindcss.com" not in html, path
        assert 'class="order-list"' in html or 'class="card' in html or 'class="kpi' in html, path


def test_i18n_catalogs_same_keys() -> None:
    ru = catalog_key_set("ru")
    en = catalog_key_set("en")
    ka = catalog_key_set("ka")
    assert ru == en == ka
    assert "nav.orders" in ru
    assert "cash.stub_title" in ru
