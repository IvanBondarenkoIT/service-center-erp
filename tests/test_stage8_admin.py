from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal
from app.models import (
    AuditLog,
    CashEntry,
    CashOpening,
    Client,
    IssueReason,
    Machine,
    OrderStatus,
    PaymentType,
    ServiceCenter,
    ServiceOrder,
    User,
)
from app.services.cash_book import build_cash_report
from tests.helpers import login, settings, user_ids

PERIOD_FROM = date(2019, 3, 1)
PERIOD_TO = date(2019, 3, 31)
DAY = date(2019, 3, 12)


def _uid() -> str:
    return uuid.uuid4().hex[:8].upper()


def _center_id(code: str) -> int:
    db = SessionLocal()
    try:
        return db.scalar(select(ServiceCenter.id).where(ServiceCenter.code == code))
    finally:
        db.close()


def _create_order(client, amount: str = "40.00", login_name: str = "mechanic_batumi") -> tuple[int, str]:
    serial = f"SN-ADM-{_uid()}"
    user_id, center_id = user_ids(login_name)
    r = client.post(
        "/orders/save",
        data={
            "order_date": DAY.isoformat(),
            "assignee_id": str(user_id),
            "service_center_id": str(center_id or ""),
            "new_machine_serial": serial,
            "new_machine_model": "Jura",
            "new_client_phone": f"599{uuid.uuid4().int % 10_000_000:07d}",
            "new_client_name": "Admin Test",
            "line_type": "work",
            "description": "repair",
            "part_code": "",
            "payment_type": "Cash",
            "is_warranty": "0",
            "amount": amount,
            "status": "in_progress",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    return int(r.headers["location"].rsplit("/", 1)[-1]), serial


def _paid_order(client, payment: str = "Cash") -> tuple[int, str]:
    login(client, "admin", settings.seed_admin_password)
    oid, serial = _create_order(client)
    assert client.post(f"/orders/{oid}/pay", follow_redirects=False).status_code == 303
    db = SessionLocal()
    try:
        order = db.get(ServiceOrder, oid)
        order.paid_at = datetime(DAY.year, DAY.month, DAY.day, 12, 0)
        db.commit()
    finally:
        db.close()
    return oid, serial


def _report_rows(serial: str):
    db = SessionLocal()
    try:
        report = build_cash_report(db, PERIOD_FROM, PERIOD_TO, _center_id("batumi"))
        return [r for r in report.income_rows if r.note == serial], report
    finally:
        db.close()


def _audit(entity: str, entity_id: int, action: str) -> bool:
    db = SessionLocal()
    try:
        return (
            db.scalar(
                select(AuditLog).where(
                    AuditLog.entity == entity,
                    AuditLog.entity_id == entity_id,
                    AuditLog.action == action,
                )
            )
            is not None
        )
    finally:
        db.close()


def test_admin_reopen_removes_from_cash_and_val(client) -> None:
    oid, serial = _paid_order(client)
    rows, _ = _report_rows(serial)
    assert len(rows) == 1

    form = client.get(f"/orders/{oid}")
    assert f"/orders/{oid}/reopen" in form.text
    assert f"/orders/{oid}/repay" not in form.text

    r = client.post(f"/orders/{oid}/reopen", follow_redirects=False)
    assert r.status_code == 303
    db = SessionLocal()
    try:
        order = db.get(ServiceOrder, oid)
        assert order.status == OrderStatus.ready
        assert order.paid_at is None
    finally:
        db.close()
    rows, _ = _report_rows(serial)
    assert rows == []
    assert _audit("order", oid, "reopen")
    assert client.post(f"/orders/{oid}/reopen", follow_redirects=False).status_code == 400


def test_admin_changes_line_payment_keeps_paid_date(client) -> None:
    oid, serial = _paid_order(client, "Cash")
    user_id, center_id = user_ids("mechanic_batumi")
    r = client.post(
        "/orders/save",
        data={
            "order_id": str(oid),
            "order_date": DAY.isoformat(),
            "assignee_id": str(user_id),
            "service_center_id": str(center_id or ""),
            "new_machine_serial": serial,
            "new_machine_model": "Jura",
            "new_client_phone": f"599{uuid.uuid4().int % 10_000_000:07d}",
            "new_client_name": "Admin Test",
            "line_type": "work",
            "description": "repair",
            "part_code": "",
            "payment_type": "Card",
            "is_warranty": "0",
            "amount": "40.00",
            "status": "issued",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    db = SessionLocal()
    try:
        order = db.get(ServiceOrder, oid)
        assert order.status == OrderStatus.issued
        assert order.paid_at.date() == DAY
        assert order.lines[0].payment_type == PaymentType.card
    finally:
        db.close()
    rows, _ = _report_rows(serial)
    assert len(rows) == 1
    assert rows[0].payment_type == PaymentType.card
    assert _audit("order", oid, "edit_issued")
    assert client.post(f"/orders/{oid}/repay", data={"payment_type": "Card"}, follow_redirects=False).status_code == 404


def test_delete_rules(client) -> None:
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    oid, _ = _create_order(client)
    assert client.post(f"/orders/{oid}/delete", follow_redirects=False).status_code == 403
    assert client.post(f"/orders/{oid}/reopen", follow_redirects=False).status_code == 403

    client.cookies.clear()
    paid_id, _ = _paid_order(client)
    assert client.post(f"/orders/{paid_id}/delete", follow_redirects=False).status_code == 400

    form = client.get(f"/orders/{oid}")
    assert f"/orders/{oid}/delete" in form.text
    r = client.post(f"/orders/{oid}/delete", follow_redirects=False)
    assert r.status_code == 303
    db = SessionLocal()
    try:
        assert db.get(ServiceOrder, oid) is None
    finally:
        db.close()
    assert _audit("order", oid, "delete")


def test_admin_edits_and_deletes_cash_entry_and_sets_opening(client) -> None:
    batumi = _center_id("batumi")
    login(client, "admin", settings.seed_admin_password)
    desc = f"adm-entry-{_uid()}"
    client.post(
        "/cash/entries",
        data={
            "kind": "expense",
            "entry_date": DAY.isoformat(),
            "amount": "15.00",
            "description": desc,
            "service_center_id": str(batumi),
        },
        follow_redirects=False,
    )
    db = SessionLocal()
    try:
        entry_id = db.scalar(select(CashEntry.id).where(CashEntry.description == desc))
    finally:
        db.close()
    assert entry_id
    _, before = _report_rows("nothing")

    page = client.get(f"/cash/entries/{entry_id}/edit")
    assert page.status_code == 200
    r = client.post(
        f"/cash/entries/{entry_id}/edit",
        data={
            "kind": "expense",
            "entry_date": DAY.isoformat(),
            "amount": "25.00",
            "description": desc,
            "service_center_id": str(batumi),
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    _, after = _report_rows("nothing")
    assert after.expense - before.expense == Decimal("10.00")
    assert _audit("cash_entry", entry_id, "edit")

    assert client.post(f"/cash/entries/{entry_id}/delete", follow_redirects=False).status_code == 303
    _, gone = _report_rows("nothing")
    assert before.expense - gone.expense == Decimal("15.00")
    assert _audit("cash_entry", entry_id, "delete")

    r = client.post(
        "/cash/openings",
        data={"service_center_id": str(batumi), "as_of_date": PERIOD_FROM.isoformat(), "amount": "333.00"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    client.post(
        "/cash/openings",
        data={"service_center_id": str(batumi), "as_of_date": PERIOD_FROM.isoformat(), "amount": "300.00"},
        follow_redirects=False,
    )
    db = SessionLocal()
    try:
        rows = list(
            db.scalars(
                select(CashOpening).where(
                    CashOpening.service_center_id == batumi,
                    CashOpening.as_of_date == PERIOD_FROM,
                )
            )
        )
        assert len(rows) == 1
        assert rows[0].amount == Decimal("300.00")
    finally:
        db.close()
    _, rep = _report_rows("nothing")
    assert rep.opening == Decimal("300.00")


def test_mechanic_cannot_edit_cash_entries(client) -> None:
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    assert client.get("/cash/entries/1/edit", follow_redirects=False).status_code == 403
    assert client.post("/cash/entries/1/delete", follow_redirects=False).status_code == 403
    r = client.post(
        "/cash/openings",
        data={"service_center_id": "1", "as_of_date": "2019-01-01", "amount": "1"},
        follow_redirects=False,
    )
    assert r.status_code == 403


def test_user_management(client) -> None:
    login(client, "admin", settings.seed_admin_password)
    assert client.get("/admin/users").status_code == 200
    new_login = f"mech_{_uid().lower()}"
    r = client.post(
        "/admin/users",
        data={
            "login": new_login,
            "full_name": "New Mech",
            "role": "mechanic",
            "service_center_id": str(_center_id("batumi")),
            "password": "secret123",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    dup = client.post(
        "/admin/users",
        data={"login": new_login, "role": "mechanic", "password": "secret123"},
        follow_redirects=False,
    )
    assert dup.status_code == 400
    new_id, _ = user_ids(new_login)
    assert _audit("user", new_id, "create")

    client.cookies.clear()
    assert login(client, new_login, "secret123").status_code == 303

    client.cookies.clear()
    login(client, "admin", settings.seed_admin_password)
    r = client.post(
        f"/admin/users/{new_id}",
        data={"full_name": "New Mech", "role": "mechanic", "service_center_id": "", "password": ""},
        follow_redirects=False,
    )
    assert r.status_code == 303
    db = SessionLocal()
    try:
        assert db.get(User, new_id).is_active is False
    finally:
        db.close()
    assert _audit("user", new_id, "edit")
    client.cookies.clear()
    assert login(client, new_login, "secret123").status_code != 303

    client.cookies.clear()
    login(client, "admin", settings.seed_admin_password)
    admin_id, _ = user_ids("admin")
    r = client.post(
        f"/admin/users/{admin_id}",
        data={"full_name": "Admin", "role": "admin", "service_center_id": "", "password": ""},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "err_self" in r.headers["location"]
    db = SessionLocal()
    try:
        assert db.get(User, admin_id).is_active is True
    finally:
        db.close()

    assert client.get("/admin/audit").status_code == 200
    assert client.get("/admin/audit?entity=user").status_code == 200


def test_dictionary_edit_and_delete_guards(client) -> None:
    login(client, "admin", settings.seed_admin_password)
    oid, serial = _create_order(client)
    db = SessionLocal()
    try:
        order = db.get(ServiceOrder, oid)
        machine_id, client_id = order.machine_id, order.client_id
    finally:
        db.close()

    r = client.post(f"/dict/machines/{machine_id}/delete", follow_redirects=False)
    assert "err_in_use" in r.headers["location"]
    r = client.post(f"/dict/clients/{client_id}/delete", follow_redirects=False)
    assert "err_in_use" in r.headers["location"]

    r = client.post(
        f"/dict/machines/{machine_id}/edit",
        data={"serial_number": serial, "model_name": "Jura E8", "erp_goods_id": ""},
        follow_redirects=False,
    )
    assert r.status_code == 303
    db = SessionLocal()
    try:
        assert db.get(Machine, machine_id).model_name == "Jura E8"
    finally:
        db.close()
    assert _audit("machine", machine_id, "edit")

    phone = f"577{uuid.uuid4().int % 10_000_000:07d}"
    client.post("/dict/clients", data={"phone": phone, "name": "Lonely"}, follow_redirects=False)
    db = SessionLocal()
    try:
        lonely = db.scalar(select(Client).where(Client.name == "Lonely", Client.phone.contains(phone[-7:])))
        lonely_id = lonely.id
    finally:
        db.close()
    r = client.post(f"/dict/clients/{lonely_id}/delete", follow_redirects=False)
    assert r.headers["location"] == "/dict/clients"
    db = SessionLocal()
    try:
        assert db.get(Client, lonely_id) is None
    finally:
        db.close()

    name = f"Reason {_uid()}"
    client.post("/dict/reasons", data={"name": name}, follow_redirects=False)
    db = SessionLocal()
    try:
        reason_id = db.scalar(select(IssueReason.id).where(IssueReason.name == name))
    finally:
        db.close()
    client.post(f"/dict/reasons/{reason_id}/edit", data={"name": name + " X"}, follow_redirects=False)
    assert _audit("reason", reason_id, "edit")
    r = client.post(f"/dict/reasons/{reason_id}/delete", follow_redirects=False)
    assert r.headers["location"] == "/dict/reasons"
    assert _audit("reason", reason_id, "delete")

    for path in ("/dict/clients", "/dict/machines", "/dict/reasons"):
        assert client.get(path).status_code == 200


def test_accountant_views_order_read_only_and_reports(client) -> None:
    oid, _ = _paid_order(client)
    client.cookies.clear()
    login(client, "accountant", settings.seed_accountant_password)
    page = client.get(f"/orders/{oid}")
    assert page.status_code == 200
    assert "is-locked" in page.text
    assert "btn-pay" not in page.text
    assert "/reopen" not in page.text
    assert 'form="order-save"' not in page.text

    saved = client.post("/orders/save", data={"order_id": str(oid)}, follow_redirects=False)
    assert saved.status_code == 303
    assert saved.headers["location"] == "/cash"
    assert client.post(f"/orders/{oid}/reopen", follow_redirects=False).status_code == 403

    reports = client.get("/reports")
    assert reports.status_code == 200
    cash = client.get("/cash", params={"date_from": PERIOD_FROM.isoformat(), "date_to": PERIOD_TO.isoformat()})
    assert f'href="/orders/{oid}"' in cash.text
    assert 'href="/reports"' in cash.text
