from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.auth import hash_password
from app.database import SessionLocal
from app.models import (
    AuditLog,
    CashEntry,
    CashEntryKind,
    CashOpening,
    LineType,
    Machine,
    OrderLine,
    OrderStatus,
    PaymentType,
    ServiceCenter,
    ServiceOrder,
    User,
    UserRole,
)
from app.services.cash_book import build_cash_report, business_today
from tests.helpers import login, settings, user_ids

PASSWORD = "trust-pass-1"


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _new_center() -> tuple[int, str]:
    """Isolated center + its own mechanic, so other tests' data cannot leak in."""
    db = SessionLocal()
    try:
        code = f"t{_uid()}"
        center = ServiceCenter(code=code, name=f"Trust {code}", city="")
        db.add(center)
        db.flush()
        login_name = f"mech_{code}"
        db.add(
            User(
                login=login_name,
                full_name="Trust mech",
                role=UserRole.mechanic,
                service_center_id=center.id,
                password_hash=hash_password(PASSWORD),
            )
        )
        db.commit()
        return center.id, login_name
    finally:
        db.close()


def _cash_order(center_id: int, order_day: date, paid_day: date | None, amount: str) -> int:
    admin_id, _ = user_ids("admin")
    db = SessionLocal()
    try:
        machine = Machine(serial_number=f"SN-TRUST-{_uid()}", model_name="Jura")
        db.add(machine)
        db.flush()
        order = ServiceOrder(
            order_date=order_day,
            assignee_id=admin_id,
            service_center_id=center_id,
            machine_id=machine.id,
            status=OrderStatus.issued,
            paid_at=(
                datetime(paid_day.year, paid_day.month, paid_day.day, 10, 0, tzinfo=timezone.utc)
                if paid_day
                else None
            ),
            lines=[
                OrderLine(
                    line_type=LineType.work,
                    payment_type=PaymentType.cash,
                    amount_work=Decimal(amount),
                    amount_parts=Decimal("0"),
                )
            ],
        )
        db.add(order)
        db.commit()
        return order.id
    finally:
        db.close()


def _entry(center_id: int, day: date, amount: str, kind=CashEntryKind.expense) -> None:
    db = SessionLocal()
    try:
        db.add(
            CashEntry(
                entry_date=day,
                service_center_id=center_id,
                kind=kind,
                amount=Decimal(amount),
                description=f"e-{_uid()}",
            )
        )
        db.commit()
    finally:
        db.close()


def _snapshot(center_id: int, day: date, amount: str, is_start: bool = False) -> None:
    db = SessionLocal()
    try:
        db.add(
            CashOpening(
                service_center_id=center_id,
                as_of_date=day,
                amount=Decimal(amount),
                is_start=is_start,
            )
        )
        db.commit()
    finally:
        db.close()


def _report(center_id: int | None, d_from: date, d_to: date):
    db = SessionLocal()
    try:
        return build_cash_report(db, d_from, d_to, center_id)
    finally:
        db.close()


def test_reconcile_inside_period(client) -> None:
    cid, _ = _new_center()
    _cash_order(cid, date(2026, 10, 3), date(2026, 10, 3), "100.00")
    _entry(cid, date(2026, 10, 5), "30.00")
    _snapshot(cid, date(2026, 10, 13), "240.00")
    _cash_order(cid, date(2026, 10, 13), date(2026, 10, 13), "50.00")

    r = _report(cid, date(2026, 10, 1), date(2026, 10, 14))
    assert r.opening == Decimal("0.00")
    assert len(r.reconcile_rows) == 1
    row = r.reconcile_rows[0]
    assert row.computed == Decimal("70.00")
    assert row.fact == Decimal("240.00")
    assert row.diff == Decimal("170.00")
    assert r.closing == Decimal("290.00")

    login(client, "admin", settings.seed_admin_password)
    page = client.get(
        "/cash", params={"date_from": "2026-10-01", "date_to": "2026-10-14", "center_id": cid}
    )
    assert 'data-reconcile-diff="170.00"' in page.text
    assert 'data-closing="290.00"' in page.text


def test_opening_includes_movements_since_snapshot() -> None:
    cid, _ = _new_center()
    _snapshot(cid, date(2026, 9, 1), "100.00")
    _cash_order(cid, date(2026, 9, 10), date(2026, 9, 10), "60.00")
    _entry(cid, date(2026, 9, 20), "25.00", CashEntryKind.collection)

    r = _report(cid, date(2026, 10, 1), date(2026, 10, 31))
    assert r.opening == Decimal("135.00")
    assert r.reconcile_rows == []
    assert r.closing == Decimal("135.00")


def test_snapshot_on_period_start_is_opening() -> None:
    cid, _ = _new_center()
    _cash_order(cid, date(2026, 9, 10), date(2026, 9, 10), "60.00")
    _snapshot(cid, date(2026, 10, 1), "500.00")
    r = _report(cid, date(2026, 10, 1), date(2026, 10, 31))
    assert r.opening == Decimal("500.00")
    assert r.reconcile_rows == []


def test_order_counted_once_by_pay_date() -> None:
    cid, _ = _new_center()
    _cash_order(cid, date(2026, 9, 30), date(2026, 10, 2), "80.00")
    sept = _report(cid, date(2026, 9, 1), date(2026, 9, 30))
    octo = _report(cid, date(2026, 10, 1), date(2026, 10, 31))
    assert sept.cash_in == Decimal("0.00")
    assert octo.cash_in == Decimal("80.00")
    assert octo.opening == Decimal("0.00")

    _cash_order(cid, date(2026, 8, 15), None, "15.00")
    aug = _report(cid, date(2026, 8, 1), date(2026, 8, 31))
    assert aug.cash_in == Decimal("15.00")


def test_all_centers_sum_reconcile() -> None:
    a, _ = _new_center()
    b, _ = _new_center()
    _snapshot(a, date(2026, 10, 5), "10.00")
    _snapshot(b, date(2026, 10, 6), "20.00")
    db = SessionLocal()
    try:
        r = build_cash_report(db, date(2026, 10, 1), date(2026, 10, 31), None)
        mine = [row for row in r.reconcile_rows if row.center_name.startswith("Trust ")]
        assert {row.fact for row in mine} >= {Decimal("10.00"), Decimal("20.00")}
    finally:
        db.close()


def test_mechanic_blocked_in_closed_period_admin_allowed(client) -> None:
    cid, mech = _new_center()
    today = business_today()
    _snapshot(cid, today, "0.00")
    login(client, mech, PASSWORD)
    past = client.post(
        "/cash/entries",
        data={"kind": "expense", "entry_date": "2020-01-01", "amount": "5.00", "description": "old"},
        follow_redirects=False,
    )
    assert past.status_code == 303
    assert "err_closed" in past.headers["location"]
    future = client.post(
        "/cash/entries",
        data={"kind": "expense", "entry_date": "2099-01-01", "amount": "5.00", "description": "future"},
        follow_redirects=False,
    )
    assert "err_future" in future.headers["location"]
    ok = client.post(
        "/cash/entries",
        data={"kind": "expense", "entry_date": today.isoformat(), "amount": "5.00", "description": "today"},
        follow_redirects=False,
    )
    assert ok.headers["location"] == "/cash/entries"
    page = client.get("/cash/entries")
    assert f'min="{today.isoformat()}"' in page.text

    db = SessionLocal()
    try:
        descs = set(db.scalars(select(CashEntry.description).where(CashEntry.service_center_id == cid)))
    finally:
        db.close()
    assert descs == {"today"}

    client.cookies.clear()
    login(client, "admin", settings.seed_admin_password)
    desc = f"admin-old-{_uid()}"
    r = client.post(
        "/cash/entries",
        data={
            "kind": "expense",
            "entry_date": "2020-01-01",
            "amount": "5.00",
            "description": desc,
            "service_center_id": str(cid),
        },
        follow_redirects=False,
    )
    assert r.headers["location"] == "/cash/entries"
    db = SessionLocal()
    try:
        entry_id = db.scalar(select(CashEntry.id).where(CashEntry.description == desc))
        log = db.scalar(
            select(AuditLog).where(AuditLog.entity == "cash_entry", AuditLog.entity_id == entry_id)
        )
        assert log is not None and "closed_period" in log.details
    finally:
        db.close()


def test_no_negative_zero_outflow(client) -> None:
    cid, _ = _new_center()
    login(client, "admin", settings.seed_admin_password)
    page = client.get(
        "/cash", params={"date_from": "2001-01-01", "date_to": "2001-01-31", "center_id": cid}
    )
    assert "−0.00" not in page.text


def test_start_of_accounting_ignores_history(client) -> None:
    cid, _ = _new_center()
    _cash_order(cid, date(2026, 9, 10), date(2026, 9, 10), "5000.00")
    _cash_order(cid, date(2026, 10, 3), date(2026, 10, 3), "100.00")
    _snapshot(cid, date(2026, 10, 13), "240.00", is_start=True)
    _cash_order(cid, date(2026, 10, 13), date(2026, 10, 13), "50.00")

    r = _report(cid, date(2026, 10, 1), date(2026, 10, 14))
    assert r.opening == Decimal("0.00")
    assert r.cash_in == Decimal("150.00")
    assert r.val == Decimal("150.00")
    assert len(r.reconcile_rows) == 1
    row = r.reconcile_rows[0]
    assert row.is_start
    assert row.computed == Decimal("100.00")
    assert r.closing == Decimal("290.00")
    assert r.has_start

    nov = _report(cid, date(2026, 11, 1), date(2026, 11, 30))
    assert nov.opening == Decimal("290.00")

    login(client, "admin", settings.seed_admin_password)
    page = client.get(
        "/cash", params={"date_from": "2026-10-01", "date_to": "2026-10-14", "center_id": cid}
    )
    assert 'data-reconcile-start="1"' in page.text
    assert "Старт учёта" in page.text
    assert "Недостача" not in page.text
    assert f"/cash/openings/{row.opening_id}/edit" in page.text


def test_regular_reconcile_after_start() -> None:
    cid, _ = _new_center()
    _cash_order(cid, date(2026, 9, 10), date(2026, 9, 10), "5000.00")
    _snapshot(cid, date(2026, 10, 13), "240.00", is_start=True)
    _cash_order(cid, date(2026, 10, 15), date(2026, 10, 15), "50.00")
    _snapshot(cid, date(2026, 10, 20), "280.00")

    r = _report(cid, date(2026, 10, 1), date(2026, 10, 31))
    start_row, regular = r.reconcile_rows
    assert start_row.is_start and not regular.is_start
    assert regular.computed == Decimal("290.00")
    assert regular.diff == Decimal("-10.00")
    assert r.closing == Decimal("280.00")


def test_edit_opening_sets_start_and_logs(client) -> None:
    cid, mech = _new_center()
    _cash_order(cid, date(2026, 9, 10), date(2026, 9, 10), "700.00")
    login(client, "admin", settings.seed_admin_password)
    client.post(
        "/cash/openings",
        data={"service_center_id": str(cid), "as_of_date": "2026-10-13", "amount": "240.00"},
        follow_redirects=False,
    )
    r = _report(cid, date(2026, 10, 1), date(2026, 10, 14))
    assert r.reconcile_rows[0].diff == Decimal("-460.00")
    opening_id = r.reconcile_rows[0].opening_id

    page = client.get(f"/cash/openings/{opening_id}/edit")
    assert page.status_code == 200
    saved = client.post(
        f"/cash/openings/{opening_id}/edit",
        data={
            "service_center_id": str(cid),
            "as_of_date": "2026-10-13",
            "amount": "250.00",
            "is_start": "1",
        },
        follow_redirects=False,
    )
    assert saved.headers["location"] == "/cash/entries"
    r = _report(cid, date(2026, 10, 1), date(2026, 10, 14))
    assert r.opening == Decimal("0.00")
    assert r.reconcile_rows[0].is_start
    assert r.closing == Decimal("250.00")
    db = SessionLocal()
    try:
        log = db.scalar(
            select(AuditLog).where(
                AuditLog.entity == "cash_opening",
                AuditLog.entity_id == opening_id,
                AuditLog.action == "edit",
            )
        )
        assert log is not None and "start" in log.details
    finally:
        db.close()

    client.post(
        "/cash/openings",
        data={"service_center_id": str(cid), "as_of_date": "2026-10-20", "amount": "1.00"},
        follow_redirects=False,
    )
    clash = client.post(
        f"/cash/openings/{opening_id}/edit",
        data={"service_center_id": str(cid), "as_of_date": "2026-10-20", "amount": "250.00"},
        follow_redirects=False,
    )
    assert "err_opening_taken" in clash.headers["location"]

    client.cookies.clear()
    login(client, mech, PASSWORD)
    assert client.get(f"/cash/openings/{opening_id}/edit", follow_redirects=False).status_code == 403
