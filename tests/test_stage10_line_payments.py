from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal
from app.models import LineType, PaymentType, PromoOffer, ServiceOrder
from app.services.cash_book import build_cash_report
from app.services.prices import set_diagnostic_price
from tests.helpers import login, settings, user_ids
from tests.test_stage4_cash import _center_id, _pay, _set_paid_at


def _serial() -> str:
    return f"SN-LN-{uuid.uuid4().hex[:8].upper()}"


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
        "new_client_name": "Mix",
        "status": "in_progress",
    }


def _make_promo(client, client_amount="0", val_amount="60.00") -> int:
    login(client, "admin", settings.seed_admin_password)
    name = f"Promo {uuid.uuid4().hex[:6]}"
    client.post(
        "/admin/prices/promos",
        data={
            "name": name,
            "client_amount": client_amount,
            "val_amount": val_amount,
            "is_active": "1",
        },
        follow_redirects=False,
    )
    db = SessionLocal()
    try:
        return db.scalar(select(PromoOffer.id).where(PromoOffer.name == name))
    finally:
        db.close()


def test_mixed_line_payments_cash_card_promo(client) -> None:
    promo_id = _make_promo(client)
    serial = _serial()
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    data = _base("mechanic_batumi", serial)
    data.update(
        {
            "line_type": ["work", "part", "promo"],
            "description": ["repair", "pump", "x"],
            "part_code": ["", "ERP-1", "should-drop"],
            "payment_type": ["Cash", "Card", "promo"],
            "is_warranty": ["0", "0", "0"],
            "amount": ["80.00", "40.00", "0"],
            "promo_id": ["", "", str(promo_id)],
        }
    )
    saved = client.post("/orders/save", data=data, follow_redirects=False)
    assert saved.status_code == 303
    oid = int(saved.headers["location"].rsplit("/", 1)[-1])
    db = SessionLocal()
    try:
        order = db.get(ServiceOrder, oid)
        kinds = [ln.line_type for ln in order.lines]
        assert LineType.work in kinds and LineType.part in kinds and LineType.promo in kinds
        promo_line = next(ln for ln in order.lines if ln.line_type == LineType.promo)
        part_line = next(ln for ln in order.lines if ln.line_type == LineType.part)
        assert promo_line.payment_type == PaymentType.promo
        assert promo_line.client_amount == Decimal("0")
        assert promo_line.val_amount == Decimal("60.00")
        assert promo_line.part_code == ""
        assert part_line.part_code == "ERP-1"
        assert order.total_amount == Decimal("120.00")
        assert order.val_total == Decimal("180.00")
    finally:
        db.close()

    form = client.get(f"/orders/{oid}")
    assert "Сводка оплаты" in form.text
    assert "Cash" in form.text and "Card" in form.text
    assert _pay(client, oid).status_code == 303
    _set_paid_at(oid, "2019-04-22")

    db = SessionLocal()
    try:
        order = db.get(ServiceOrder, oid)
        assert {ln.payment_type for ln in order.lines} >= {PaymentType.cash, PaymentType.card, PaymentType.promo}
        report = build_cash_report(
            db,
            date.fromisoformat("2019-04-01"),
            date.fromisoformat("2019-04-30"),
            _center_id("batumi"),
        )
        rows = [r for r in report.income_rows if r.note == serial]
        assert len(rows) == 1
        assert rows[0].cash == Decimal("80.00")
        assert rows[0].card == Decimal("40.00")
        assert rows[0].promo == Decimal("60.00")
        assert rows[0].amount == Decimal("180.00")
        assert report.closing == report.opening + report.cash_in - report.expense - report.collection
    finally:
        db.close()


def test_diagnostic_uses_setting_and_can_override(client) -> None:
    login(client, "admin", settings.seed_admin_password)
    db = SessionLocal()
    try:
        set_diagnostic_price(db, "25.00")
        db.commit()
    finally:
        db.close()
    page = client.get("/admin/prices")
    assert page.status_code == 200
    assert "25.00" in page.text

    serial = _serial()
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    form = client.get("/orders/intake")
    # new order via save
    data = _base("mechanic_batumi", serial)
    data.update(
        {
            "line_type": "diagnostic",
            "description": "Диагностика",
            "part_code": "",
            "payment_type": "Cash",
            "is_warranty": "0",
            "amount": "25.00",
            "promo_id": "",
        }
    )
    saved = client.post("/orders/save", data=data, follow_redirects=False)
    oid = int(saved.headers["location"].rsplit("/", 1)[-1])
    db = SessionLocal()
    try:
        assert db.get(ServiceOrder, oid).lines[0].client_amount == Decimal("25.00")
    finally:
        db.close()

    data["order_id"] = str(oid)
    data["amount"] = "40.00"
    client.post("/orders/save", data=data, follow_redirects=False)
    db = SessionLocal()
    try:
        assert db.get(ServiceOrder, oid).lines[0].client_amount == Decimal("40.00")
        assert db.get(ServiceOrder, oid).lines[0].line_type.value == "diagnostic"
    finally:
        db.close()


def test_pay_button_saves_then_issues(client) -> None:
    serial = _serial()
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    data = _base("mechanic_batumi", serial)
    data.update(
        {
            "line_type": "work",
            "description": "draft",
            "part_code": "",
            "payment_type": "Cash",
            "is_warranty": "0",
            "amount": "5.00",
            "promo_id": "",
        }
    )
    saved = client.post("/orders/save", data=data, follow_redirects=False)
    oid = int(saved.headers["location"].rsplit("/", 1)[-1])
    form = client.get(f"/orders/{oid}")
    assert 'name="after_save" value="pay"' in form.text
    assert f'action="/orders/{oid}/pay"' not in form.text
    assert 'form="order-save"' in form.text

    data["order_id"] = str(oid)
    data["description"] = "final repair"
    data["payment_type"] = "Card"
    data["amount"] = "77.00"
    data["after_save"] = "pay"
    paid = client.post("/orders/save", data=data, follow_redirects=False)
    assert paid.status_code == 303
    db = SessionLocal()
    try:
        order = db.get(ServiceOrder, oid)
        assert order.status.value == "issued"
        assert order.paid_at is not None
        assert order.lines[0].description == "final repair"
        assert order.lines[0].payment_type == PaymentType.card
        assert order.lines[0].client_amount == Decimal("77.00")
    finally:
        db.close()


def test_pay_keeps_line_methods(client) -> None:
    serial = _serial()
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    data = _base("mechanic_batumi", serial)
    data.update(
        {
            "line_type": "work",
            "description": "repair",
            "part_code": "",
            "payment_type": "Card",
            "is_warranty": "0",
            "amount": "10.00",
            "promo_id": "",
        }
    )
    saved = client.post("/orders/save", data=data, follow_redirects=False)
    oid = int(saved.headers["location"].rsplit("/", 1)[-1])
    assert _pay(client, oid).status_code == 303
    db = SessionLocal()
    try:
        order = db.get(ServiceOrder, oid)
        assert order.lines[0].payment_type == PaymentType.card
    finally:
        db.close()


def test_warranty_does_not_wipe_promo_line(client) -> None:
    promo_id = _make_promo(client, "0", "60.00")
    serial = _serial()
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    data = _base("mechanic_batumi", serial)
    data.update(
        {
            "line_type": "promo",
            "description": "x",
            "part_code": "",
            "payment_type": "garanty",
            "is_warranty": "1",
            "amount": "0",
            "promo_id": str(promo_id),
        }
    )
    saved = client.post("/orders/save", data=data, follow_redirects=False)
    oid = int(saved.headers["location"].rsplit("/", 1)[-1])
    db = SessionLocal()
    try:
        line = db.get(ServiceOrder, oid).lines[0]
        assert line.line_type == LineType.promo
        assert line.payment_type == PaymentType.promo
        assert line.val_amount == Decimal("60.00")
    finally:
        db.close()


def test_cash_income_one_row_per_order_and_method_filter(client) -> None:
    promo_id = _make_promo(client)
    serial = _serial()
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    data = _base("mechanic_batumi", serial)
    data.update(
        {
            "line_type": ["work", "part", "promo"],
            "description": ["repair", "pump", "x"],
            "part_code": ["", "ERP-1", ""],
            "payment_type": ["Cash", "Card", "promo"],
            "is_warranty": ["0", "0", "0"],
            "amount": ["80.00", "40.00", "0"],
            "promo_id": ["", "", str(promo_id)],
        }
    )
    saved = client.post("/orders/save", data=data, follow_redirects=False)
    oid = int(saved.headers["location"].rsplit("/", 1)[-1])
    assert _pay(client, oid).status_code == 303
    _set_paid_at(oid, "2019-04-22")
    login(client, "admin", settings.seed_admin_password)
    params = {"date_from": "2019-04-01", "date_to": "2019-04-30", "center_id": _center_id("batumi")}
    page = client.get("/cash", params=params)
    assert page.status_code == 200
    html = page.text
    assert html.count(f'data-order-income="{oid}"') == 1
    assert "80.00" in html and "40.00" in html and "60.00" in html
    assert "Касса — только наличные" in html
    assert "method=Card" in html
    only_card = client.get("/cash", params=params | {"method": "Card"})
    assert serial in only_card.text
    assert f'data-order-income="{oid}"' in only_card.text
    only_transfer = client.get("/cash", params=params | {"method": "perechisleniye"})
    assert serial not in only_transfer.text


def test_mechanic_forbidden_prices_page(client) -> None:
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    assert client.get("/admin/prices", follow_redirects=False).status_code == 403
