from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database import SessionLocal
from app.models import OrderStatus, ServiceOrder
from tests.helpers import login, settings, user_ids


def _serial() -> str:
    return f"SN-{uuid.uuid4().hex[:10].upper()}"


def _phone() -> str:
    return f"599{uuid.uuid4().int % 10_000_000:07d}"


def _payload(login_name: str, serial: str, **extra) -> dict[str, str]:
    user_id, center_id = user_ids(login_name)
    data = {
        "order_date": date.today().isoformat(),
        "assignee_id": str(user_id),
        "service_center_id": str(center_id or ""),
        "new_machine_serial": serial,
        "new_machine_model": extra.get("model", "Jura E8"),
        "new_client_phone": extra.get("phone", _phone()),
        "new_client_name": extra.get("name", "Nino"),
        "line_type": extra.get("line_type", "work"),
        "description": extra.get("description", "cleaning"),
        "part_code": extra.get("part_code", ""),
        "payment_type": extra.get("payment_type", "Cash"),
        "amount_work": extra.get("amount_work", "25.50"),
        "amount_parts": extra.get("amount_parts", "10.00"),
        "status": extra.get("status", "in_progress"),
        "comment": extra.get("comment", ""),
    }
    if extra.get("order_id"):
        data["order_id"] = str(extra["order_id"])
    return data


def _save(client, login_name: str, password: str, serial: str, **extra):
    login(client, login_name, password)
    return client.post(
        "/orders/save",
        data=_payload(login_name, serial, **extra),
        follow_redirects=False,
    )


def _order_id(location: str) -> int:
    return int(location.rstrip("/").rsplit("/", 1)[-1])


def _load_order(order_id: int) -> ServiceOrder | None:
    db = SessionLocal()
    try:
        return db.scalar(
            select(ServiceOrder)
            .options(joinedload(ServiceOrder.lines), joinedload(ServiceOrder.machine))
            .where(ServiceOrder.id == order_id)
        )
    finally:
        db.close()


def test_create_order_default_status_and_total(client) -> None:
    serial = _serial()
    payload = _payload("mechanic_batumi", serial)
    payload.pop("status")
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    r = client.post("/orders/save", data=payload, follow_redirects=False)
    assert r.status_code == 303
    oid = _order_id(r.headers["location"])
    order = _load_order(oid)
    assert order is not None
    assert order.status == OrderStatus.in_progress
    assert order.total_amount == Decimal("35.50")
    assert order.machine.serial_number == serial


def test_serial_required(client) -> None:
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    payload = _payload("mechanic_batumi", "")
    r = client.post("/orders/save", data=payload, follow_redirects=False)
    assert r.status_code == 400


def test_status_change_shows_on_list_card(client) -> None:
    serial = _serial()
    r = _save(client, "mechanic_batumi", settings.seed_mechanic_password, serial)
    oid = _order_id(r.headers["location"])
    client.cookies.clear()
    r2 = _save(
        client,
        "mechanic_batumi",
        settings.seed_mechanic_password,
        serial,
        order_id=oid,
        status="waiting_part",
        phone=_phone(),
    )
    assert r2.status_code == 303
    order = _load_order(oid)
    assert order is not None
    assert order.status == OrderStatus.waiting_part
    listing = client.get("/")
    assert listing.status_code == 200
    assert f'data-status="waiting_part"' in listing.text
    assert serial in listing.text
    assert "Ожидание детали" in listing.text


def test_issued_status_on_card(client) -> None:
    serial = _serial()
    r = _save(client, "mechanic_batumi", settings.seed_mechanic_password, serial)
    oid = _order_id(r.headers["location"])
    client.cookies.clear()
    r2 = _save(
        client,
        "mechanic_batumi",
        settings.seed_mechanic_password,
        serial,
        order_id=oid,
        status="issued",
        phone=_phone(),
    )
    assert r2.status_code == 303
    order = _load_order(oid)
    assert order is not None
    assert order.status == OrderStatus.issued
    listing = client.get("/")
    assert 'data-status="issued"' in listing.text
    assert "Выдан" in listing.text


def test_mechanic_cannot_access_foreign_order_admin_sees_both(client) -> None:
    serial_a = _serial()
    serial_b = _serial()
    ra = _save(client, "mechanic_batumi", settings.seed_mechanic_password, serial_a)
    oid_a = _order_id(ra.headers["location"])
    client.cookies.clear()
    rb = _save(client, "mechanic_tbilisi", settings.seed_mechanic_password, serial_b)
    assert rb.status_code == 303

    listing_b = client.get("/")
    assert serial_b in listing_b.text
    assert serial_a not in listing_b.text

    foreign = client.get(f"/orders/{oid_a}", follow_redirects=False)
    assert foreign.status_code == 403
    steal = client.post(
        "/orders/save",
        data=_payload("mechanic_tbilisi", serial_a, order_id=oid_a),
        follow_redirects=False,
    )
    assert steal.status_code == 403

    client.cookies.clear()
    login(client, "admin", settings.seed_admin_password)
    admin_list = client.get("/")
    assert serial_a in admin_list.text
    assert serial_b in admin_list.text


def test_search_by_serial_and_phone(client) -> None:
    serial = _serial()
    phone = _phone()
    _save(
        client,
        "mechanic_batumi",
        settings.seed_mechanic_password,
        serial,
        phone=phone,
        name="Search Client",
    )
    by_sn = client.get("/", params={"q": serial})
    assert by_sn.status_code == 200
    assert serial in by_sn.text
    by_phone = client.get("/", params={"q": phone})
    assert phone in by_phone.text


def test_history_partial_for_existing_machine(client) -> None:
    serial = _serial()
    _save(client, "mechanic_batumi", settings.seed_mechanic_password, serial, comment="first visit")
    hist = client.get("/orders/partials/history", params={"serial": serial})
    assert hist.status_code == 200
    assert serial in hist.text
    assert "first visit" in hist.text or date.today().strftime("%d.%m.%Y") in hist.text


def test_mechanic_dicts_forbidden_erp_suggest_ok(client) -> None:
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    denied = client.get("/dict/clients", follow_redirects=False)
    assert denied.status_code in (403, 303)
    if denied.status_code == 200:
        raise AssertionError("mechanic must not see dictionary list")
    suggest = client.get("/dict/erp-suggest", params={"q": "jura", "kind": "machine"})
    assert suggest.status_code == 200


def test_new_order_form_has_chips_status_gel(client) -> None:
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    page = client.get("/orders/new")
    assert page.status_code == 200
    html = page.text
    assert 'name="status"' in html
    assert "chip-row" in html
    assert "GEL" in html
    assert 'name="new_machine_serial"' in html
    assert "/dict/erp-suggest" in html
    assert "/dict/clients" not in html
