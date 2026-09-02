from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import load_workbook
from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import CashEntry, CashEntryKind, CashOpening, ServiceCenter
from tests.helpers import login, settings, user_ids

PERIOD_FROM = "2020-06-01"
PERIOD_TO = "2020-06-30"
DAY = "2020-06-15"


def _serial() -> str:
    return f"SN-CASH-{uuid.uuid4().hex[:8].upper()}"


def _phone() -> str:
    return f"555{uuid.uuid4().int % 10_000_000:07d}"


def _center_id(code: str) -> int:
    db = SessionLocal()
    try:
        center = db.scalar(select(ServiceCenter).where(ServiceCenter.code == code))
        assert center is not None
        return center.id
    finally:
        db.close()


def _order_payload(login_name: str, serial: str, payment_type: str, work: str, parts: str) -> dict:
    user_id, center_id = user_ids(login_name)
    return {
        "order_date": DAY,
        "assignee_id": str(user_id),
        "service_center_id": str(center_id or ""),
        "new_machine_serial": serial,
        "new_machine_model": "Jura",
        "new_client_phone": _phone(),
        "new_client_name": "Cash Test",
        "line_type": "work",
        "description": "repair",
        "part_code": "",
        "payment_type": payment_type,
        "amount_work": work,
        "amount_parts": parts,
        "status": "issued",
    }


def _set_opening(center_id: int, amount: str, as_of: str = PERIOD_FROM) -> None:
    db = SessionLocal()
    try:
        db.add(
            CashOpening(
                service_center_id=center_id,
                as_of_date=date.fromisoformat(as_of),
                amount=Decimal(amount),
            )
        )
        db.commit()
    finally:
        db.close()


def test_cash_formula_excludes_card_from_till(client) -> None:
    batumi = _center_id("batumi")
    _set_opening(batumi, "100.00")
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    cash_order = client.post(
        "/orders/save",
        data=_order_payload("mechanic_batumi", _serial(), "Cash", "40.00", "10.00"),
        follow_redirects=False,
    )
    assert cash_order.status_code == 303
    card_order = client.post(
        "/orders/save",
        data=_order_payload("mechanic_batumi", _serial(), "Card", "30.00", "0"),
        follow_redirects=False,
    )
    assert card_order.status_code == 303
    warranty = client.post(
        "/orders/save",
        data=_order_payload("mechanic_batumi", _serial(), "garanty", "99.00", "0"),
        follow_redirects=False,
    )
    assert warranty.status_code == 303

    exp = client.post(
        "/cash/entries",
        data={
            "kind": "expense",
            "entry_date": DAY,
            "amount": "20.00",
            "description": "filters",
            "service_center_id": str(batumi),
        },
        follow_redirects=False,
    )
    assert exp.status_code == 303
    coll = client.post(
        "/cash/entries",
        data={
            "kind": "collection",
            "entry_date": DAY,
            "amount": "10.00",
            "description": "bank",
            "subtype": "bank",
            "service_center_id": str(batumi),
        },
        follow_redirects=False,
    )
    assert coll.status_code == 303

    client.cookies.clear()
    login(client, "admin", settings.seed_admin_password)
    page = client.get(
        "/cash",
        params={"date_from": PERIOD_FROM, "date_to": PERIOD_TO, "center_id": batumi},
    )
    assert page.status_code == 200
    html = page.text
    assert 'data-opening="100.00"' in html
    assert 'data-cash-in="50.00"' in html
    assert 'data-card-in="30.00"' in html
    assert 'data-expense="20.00"' in html
    assert 'data-collection="10.00"' in html
    assert 'data-closing="120.00"' in html
    assert "99.00" not in html


def test_mechanic_expense_own_center_only(client) -> None:
    batumi = _center_id("batumi")
    tbilisi = _center_id("tbilisi")
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    ok = client.post(
        "/cash/entries",
        data={
            "kind": "expense",
            "entry_date": date.today().isoformat(),
            "amount": "7.50",
            "description": "own-center",
            "service_center_id": str(batumi),
        },
        follow_redirects=False,
    )
    assert ok.status_code == 303
    db = SessionLocal()
    try:
        row = db.scalar(
            select(CashEntry).where(CashEntry.description == "own-center")
        )
        assert row is not None
        assert row.kind == CashEntryKind.expense
        assert row.service_center_id == batumi
        assert row.amount == Decimal("7.50")
    finally:
        db.close()

    again = client.post(
        "/cash/entries",
        data={
            "kind": "expense",
            "entry_date": date.today().isoformat(),
            "amount": "7.50",
            "description": "own-center",
            "service_center_id": str(batumi),
        },
        follow_redirects=False,
    )
    assert again.status_code == 303
    db = SessionLocal()
    try:
        count = db.scalar(
            select(func.count()).select_from(CashEntry).where(CashEntry.description == "own-center")
        )
        assert count == 1
    finally:
        db.close()

    denied = client.post(
        "/cash/entries",
        data={
            "kind": "expense",
            "entry_date": date.today().isoformat(),
            "amount": "1.00",
            "description": "foreign-center",
            "service_center_id": str(tbilisi),
        },
        follow_redirects=False,
    )
    assert denied.status_code == 403


def test_accountant_read_only_cash(client) -> None:
    login(client, "accountant", settings.seed_accountant_password)
    report = client.get("/cash")
    assert report.status_code == 200
    assert "data-closing" in report.text
    posted = client.post(
        "/cash/entries",
        data={
            "kind": "expense",
            "entry_date": date.today().isoformat(),
            "amount": "1.00",
            "description": "should-fail",
        },
        follow_redirects=False,
    )
    assert posted.status_code == 403
    orders = client.get("/orders/new", follow_redirects=False)
    assert orders.status_code == 303
    sync = client.post(
        "/dict/erp-catalog/sync",
        data={"mode": "incremental"},
        follow_redirects=False,
    )
    assert sync.status_code == 403


def test_admin_report_lists_all_centers(client) -> None:
    login(client, "admin", settings.seed_admin_password)
    page = client.get("/cash")
    assert page.status_code == 200
    assert "Сервис Батуми" in page.text
    assert "Сервис Тбилиси" in page.text
    assert "Сервис Тбилиси 2" in page.text


def test_cash_xlsx_has_period(client) -> None:
    login(client, "admin", settings.seed_admin_password)
    r = client.get(
        "/cash.xlsx",
        params={"date_from": PERIOD_FROM, "date_to": PERIOD_TO},
    )
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    assert PERIOD_FROM in r.headers.get("content-disposition", "")
    assert PERIOD_TO in r.headers.get("content-disposition", "")
    wb = load_workbook(BytesIO(r.content))
    header = str(wb.active["A1"].value)
    assert PERIOD_FROM in header
    assert PERIOD_TO in header
