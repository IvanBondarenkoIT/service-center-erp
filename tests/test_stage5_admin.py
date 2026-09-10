from __future__ import annotations

import uuid

from tests.helpers import login, settings, user_ids


REPORT_DAY = "2019-08-20"


def _serial() -> str:
    return f"SN-RPT-{uuid.uuid4().hex[:8].upper()}"


def _phone() -> str:
    return f"577{uuid.uuid4().int % 10_000_000:07d}"


def _order(login_name: str, payment: str, work: str) -> dict[str, str]:
    user_id, center_id = user_ids(login_name)
    return {
        "order_date": REPORT_DAY,
        "assignee_id": str(user_id),
        "service_center_id": str(center_id or ""),
        "new_machine_serial": _serial(),
        "new_machine_model": "Report Machine",
        "new_client_phone": _phone(),
        "new_client_name": "Report",
        "line_type": "work",
        "description": "report-line",
        "part_code": "",
        "payment_type": payment,
        "amount_work": work,
        "amount_parts": "0",
        "status": "issued",
    }


def test_admin_reports_by_center_and_payment(client) -> None:
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    a = client.post(
        "/orders/save",
        data=_order("mechanic_batumi", "Cash", "111.11"),
        follow_redirects=False,
    )
    assert a.status_code == 303
    client.cookies.clear()
    login(client, "mechanic_tbilisi1", settings.seed_mechanic_password)
    b = client.post(
        "/orders/save",
        data=_order("mechanic_tbilisi1", "Card", "222.22"),
        follow_redirects=False,
    )
    assert b.status_code == 303
    client.cookies.clear()
    login(client, "admin", settings.seed_admin_password)
    page = client.get("/reports", params={"date_from": REPORT_DAY, "date_to": REPORT_DAY})
    assert page.status_code == 200
    html = page.text
    assert "Сервис Батуми" in html
    assert "Сервис Тбилиси" in html
    assert 'data-payment="Cash"' in html
    assert 'data-payment="Card"' in html
    assert 'data-amount="111.11"' in html
    assert 'data-amount="222.22"' in html


def test_mechanic_reports_and_dicts_forbidden(client) -> None:
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    reports = client.get("/reports", follow_redirects=False)
    assert reports.status_code == 403
    clients = client.get("/dict/clients", follow_redirects=False)
    assert clients.status_code in (403, 303)
    assert clients.status_code != 200


def test_admin_clients_ok(client) -> None:
    login(client, "admin", settings.seed_admin_password)
    page = client.get("/dict/clients")
    assert page.status_code == 200
    assert 'name="phone"' in page.text


def test_accountant_erp_catalog_redirects_to_cash(client) -> None:
    login(client, "accountant", settings.seed_accountant_password)
    page = client.get("/dict/erp-catalog", follow_redirects=False)
    assert page.status_code == 303
    assert page.headers["location"] == "/cash"


def test_erp_sync_acl(client) -> None:
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    mech = client.post(
        "/dict/erp-catalog/sync",
        data={"mode": "incremental"},
        follow_redirects=False,
    )
    assert mech.status_code == 403
    client.cookies.clear()
    login(client, "accountant", settings.seed_accountant_password)
    acc = client.post(
        "/dict/erp-catalog/sync",
        data={"mode": "incremental"},
        follow_redirects=False,
    )
    assert acc.status_code == 403
    client.cookies.clear()
    login(client, "admin", settings.seed_admin_password)
    admin = client.post(
        "/dict/erp-catalog/sync",
        data={"mode": "incremental"},
        follow_redirects=False,
    )
    assert admin.status_code != 403
