from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database import SessionLocal
from app.models import OrderEvent, OrderStatus, PaymentType, ServiceOrder
from app.services.cash_book import build_cash_report
from tests.helpers import login, settings, user_ids
from tests.test_stage4_cash import _center_id, _pay, _set_paid_at


def _serial() -> str:
    return f"SN-WH-{uuid.uuid4().hex[:8].upper()}"


def _phone() -> str:
    return f"599{uuid.uuid4().int % 10_000_000:07d}"


def _base(login_name: str, serial: str) -> dict:
    user_id, center_id = user_ids(login_name)
    return {
        "order_date": "2019-04-22",
        "assignee_id": str(user_id),
        "service_center_id": str(center_id or ""),
        "new_machine_serial": serial,
        "new_machine_model": "Jura",
        "new_client_phone": _phone(),
        "new_client_name": "Warranty",
        "status": "in_progress",
    }


def test_warranty_eur_stays_out_of_till_and_val(client) -> None:
    serial = _serial()
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    data = _base("mechanic_batumi", serial)
    data.update(
        {
            "line_type": ["work", "work"],
            "description": ["paid work", "warranty seal"],
            "part_code": ["", ""],
            "payment_type": ["Cash", "garanty"],
            "is_warranty": ["0", "1"],
            "amount": ["80.00", "0"],
            "warranty_eur": ["0", "5.00"],
            "promo_id": ["", ""],
        }
    )
    saved = client.post("/orders/save", data=data, follow_redirects=False)
    assert saved.status_code == 303
    oid = int(saved.headers["location"].rsplit("/", 1)[-1])
    assert _pay(client, oid).status_code == 303
    _set_paid_at(oid, "2019-04-22")
    db = SessionLocal()
    try:
        order = db.scalars(
            select(ServiceOrder).options(joinedload(ServiceOrder.lines)).where(ServiceOrder.id == oid)
        ).unique().one()
        assert order.total_amount == Decimal("80.00")
        assert order.warranty_eur_total == Decimal("5.00")
        assert {ln.payment_type for ln in order.lines} >= {PaymentType.cash, PaymentType.warranty}
        report = build_cash_report(db, date(2019, 4, 1), date(2019, 4, 30), _center_id("batumi"))
        rows = [r for r in report.income_rows if r.note == serial]
        assert len(rows) == 1
        assert rows[0].cash == Decimal("80.00")
        assert rows[0].warranty_eur == Decimal("5.00")
        assert rows[0].amount == Decimal("80.00")
        assert report.val == report.cash_in + report.card_in + report.transfer_in + report.promo_in
        assert report.warranty_in >= Decimal("5.00")
    finally:
        db.close()
    login(client, "admin", settings.seed_admin_password)
    params = {"date_from": "2019-04-01", "date_to": "2019-04-30", "center_id": _center_id("batumi")}
    page = client.get("/cash", params=params)
    assert page.status_code == 200
    assert "5.00" in page.text
    assert "EUR" in page.text
    assert "не в кассе и не в вале" in page.text
    only_w = client.get("/cash", params=params | {"method": "garanty"})
    assert serial in only_w.text
    reports = client.get("/reports", params=params)
    assert reports.status_code == 200
    assert 'data-warranty-in="' in reports.text


def test_list_shows_pay_chips_and_paid_date(client) -> None:
    serial = _serial()
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    data = _base("mechanic_batumi", serial)
    data.update(
        {
            "line_type": ["work", "work"],
            "description": ["paid", "warr"],
            "part_code": ["", ""],
            "payment_type": ["Card", "garanty"],
            "is_warranty": ["0", "1"],
            "amount": ["40.00", "0"],
            "warranty_eur": ["0", "3.50"],
            "status": "ready",
        }
    )
    saved = client.post("/orders/save", data=data, follow_redirects=False)
    oid = int(saved.headers["location"].rsplit("/", 1)[-1])
    assert _pay(client, oid).status_code == 303
    listing = client.get("/?status=issued")
    assert listing.status_code == 200
    assert "pay-chip-Card" in listing.text
    assert "pay-chip-garanty" in listing.text
    assert "3.50" in listing.text
    assert "EUR" in listing.text
    assert "Оплачен" in listing.text
    form = client.get(f"/orders/{oid}")
    assert form.status_code == 200
    assert "is-warranty-pay" in form.text
    assert "Оплачен" in form.text
    assert "История заказа" in form.text
    assert "Создан" in form.text
    assert "Оплачен" in form.text


def test_order_events_status_pay_reopen(client) -> None:
    serial = _serial()
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    data = _base("mechanic_batumi", serial)
    data.update(
        {
            "line_type": "work",
            "description": "fix",
            "payment_type": "Cash",
            "is_warranty": "0",
            "amount": "20.00",
            "status": "in_progress",
        }
    )
    saved = client.post("/orders/save", data=data, follow_redirects=False)
    oid = int(saved.headers["location"].rsplit("/", 1)[-1])
    data["order_id"] = str(oid)
    data["status"] = "waiting_part"
    assert client.post("/orders/save", data=data, follow_redirects=False).status_code == 303
    data["status"] = "ready"
    assert client.post("/orders/save", data=data, follow_redirects=False).status_code == 303
    assert _pay(client, oid).status_code == 303
    login(client, "admin", settings.seed_admin_password)
    assert client.post(f"/orders/{oid}/reopen", follow_redirects=False).status_code == 303
    db = SessionLocal()
    try:
        actions = [
            ev.action
            for ev in db.scalars(
                select(OrderEvent).where(OrderEvent.order_id == oid).order_by(OrderEvent.id)
            )
        ]
        assert actions[0] == "created"
        assert "status" in actions
        assert "paid" in actions
        assert "reopened" in actions
    finally:
        db.close()
    hist = client.get("/admin/order-history")
    assert hist.status_code == 200
    assert f"/orders/{oid}" in hist.text
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    assert client.get("/admin/order-history", follow_redirects=False).status_code == 403
    login(client, "accountant", settings.seed_accountant_password)
    assert client.get("/admin/order-history").status_code == 200
