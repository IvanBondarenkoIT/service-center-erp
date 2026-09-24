from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.database import SessionLocal
from app.models import OrderStatus, ServiceOrder
from app.services.serial_scan import serial_from_scan
from tests.helpers import login, settings, user_ids


def _serial() -> str:
    return f"SN-IN-{uuid.uuid4().hex[:8].upper()}"


def _phone() -> str:
    return f"555{uuid.uuid4().int % 10_000_000:07d}"


def _order_id(location: str) -> int:
    return int(location.rstrip("/").rsplit("/", 1)[-1])


def test_serial_from_scan_plain_and_url() -> None:
    assert serial_from_scan("  ABC-123  ") == "ABC-123"
    assert serial_from_scan("https://example.com/m/SN-99?x=1") == "SN-99"
    assert serial_from_scan("https://example.com/scan?sn=JURA42") == "JURA42"
    assert serial_from_scan("sn:DELONGHI1") == "DELONGHI1"


def test_orders_new_redirects_to_intake(client) -> None:
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    r = client.get("/orders/new", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/orders/intake"


def test_intake_requires_serial_and_phone(client) -> None:
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    no_sn = client.post(
        "/orders/intake",
        data={"new_client_phone": _phone(), "new_client_name": "A", "new_machine_serial": ""},
        follow_redirects=False,
    )
    assert no_sn.status_code == 400
    no_phone = client.post(
        "/orders/intake",
        data={"new_client_phone": "", "new_machine_serial": _serial()},
        follow_redirects=False,
    )
    assert no_phone.status_code == 400


def test_intake_creates_order_and_redirects(client) -> None:
    serial = _serial()
    phone = _phone()
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    page = client.get("/orders/intake")
    assert page.status_code == 200
    assert "Приёмка" in page.text
    assert "scan-qr-btn" in page.text
    assert "/static/intake-scan.js" in page.text

    r = client.post(
        "/orders/intake",
        data={
            "new_machine_serial": f"https://label.local/q?serial={serial}",
            "new_client_phone": phone,
            "new_client_name": "Intake Client",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    oid = _order_id(r.headers["location"])
    db = SessionLocal()
    try:
        order = db.scalar(
            select(ServiceOrder)
            .options(joinedload(ServiceOrder.machine), joinedload(ServiceOrder.client))
            .where(ServiceOrder.id == oid)
        )
        assert order is not None
        assert order.status == OrderStatus.in_progress
        assert order.machine.serial_number == serial
        assert order.client is not None
        assert phone[-9:] in order.client.phone or order.client.phone.endswith(phone[-9:])
        assert order.client.name == "Intake Client"
        assert order.order_date == date.today()
        user_id, _ = user_ids("mechanic_batumi")
        assert order.assignee_id == user_id
    finally:
        db.close()


def test_history_by_client_shows_comment(client) -> None:
    serial = _serial()
    phone = _phone()
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    created = client.post(
        "/orders/intake",
        data={
            "new_machine_serial": serial,
            "new_client_phone": phone,
            "new_client_name": "Hist",
        },
        follow_redirects=False,
    )
    oid = _order_id(created.headers["location"])
    db = SessionLocal()
    try:
        order = db.get(ServiceOrder, oid)
        assert order is not None
        order.comment = "note-from-past-visit"
        db.commit()
    finally:
        db.close()

    hist = client.get("/orders/partials/history-by-client", params={"phone": phone})
    assert hist.status_code == 200
    assert "note-from-past-visit" in hist.text
    assert serial in hist.text
