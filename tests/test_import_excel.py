from __future__ import annotations

import uuid
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.database import SessionLocal
from app.models import OrderStatus, ServiceOrder
from app.services.import_excel import import_excel


def _write_sample(path: Path, comment: str, rows: int = 1) -> None:
    phone = f"599{uuid.uuid4().int % 10_000_000:07d}"
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(
        [
            "Date",
            "",
            "Model",
            "Comment",
            "Owner",
            "Payment",
            "Phone",
            "Total",
            "Work",
            "Parts",
            "Part",
            "Part SN",
        ]
    )
    for _ in range(rows):
        ws.append(
            [
                datetime(2018, 5, 10),
                None,
                "Jura E8",
                comment,
                "Gio",
                "Cash",
                phone,
                50,
                40,
                10,
                "",
                "",
            ]
        )
    wb.save(path)


def test_excel_import_respects_date_range(tmp_path) -> None:
    comment = f"imported-range-{uuid.uuid4().hex[:8]}"
    path = tmp_path / "orders.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["Date", "", "Model", "Comment", "Owner", "Payment", "Phone", "Total", "Work", "Parts", "Part", "Part SN"])
    phone = f"599{uuid.uuid4().int % 10_000_000:07d}"
    ws.append([datetime(2026, 7, 15), None, "Jura E8", comment, "Gio", "Cash", phone, 50, 40, 10, "", ""])
    ws.append([datetime(2026, 8, 10), None, "Jura E8", comment, "Gio", "Cash", phone, 50, 40, 10, "", ""])
    ws.append([datetime(2026, 9, 2), None, "Jura E8", comment, "Gio", "Cash", phone, 50, 40, 10, "", ""])
    ws.append([datetime(2026, 10, 1), None, "Jura E8", comment, "Gio", "Cash", phone, 50, 40, 10, "", ""])
    wb.save(path)
    db = SessionLocal()
    try:
        from datetime import date

        stats = import_excel(
            db,
            path,
            default_center_code="batumi",
            date_from=date(2026, 8, 1),
            date_to=date(2026, 9, 30),
        )
        count = db.scalar(
            select(func.count()).select_from(ServiceOrder).where(ServiceOrder.comment == comment)
        )
    finally:
        db.close()
    assert stats["orders"] == 2
    assert count == 2


def test_excel_import_marks_orders_issued(tmp_path, client) -> None:
    comment = f"imported-history-{uuid.uuid4().hex[:8]}"
    path = tmp_path / "orders.xlsx"
    _write_sample(path, comment)
    db = SessionLocal()
    try:
        stats = import_excel(db, path, default_center_code="batumi")
        order = db.scalar(
            select(ServiceOrder)
            .options(joinedload(ServiceOrder.machine))
            .where(ServiceOrder.comment == comment)
        )
        assert stats["orders"] == 1
        assert order is not None
        assert order.status == OrderStatus.issued
        assert order.paid_at is not None
        assert order.paid_at.date() == date(2018, 5, 10)
        serial = order.machine.serial_number
        center_id = order.service_center_id
    finally:
        db.close()

    from tests.helpers import login, settings

    login(client, "admin", settings.seed_admin_password)
    page = client.get(
        "/cash",
        params={
            "date_from": "2018-05-10",
            "date_to": "2018-05-10",
            "center_id": center_id,
        },
    )
    assert page.status_code == 200
    assert serial in page.text


def test_excel_import_skips_duplicates(tmp_path) -> None:
    comment = f"imported-dup-{uuid.uuid4().hex[:8]}"
    path = tmp_path / "orders.xlsx"
    _write_sample(path, comment, rows=2)
    db = SessionLocal()
    try:
        first = import_excel(db, path, default_center_code="batumi")
        second = import_excel(db, path, default_center_code="batumi")
        count = db.scalar(
            select(func.count()).select_from(ServiceOrder).where(ServiceOrder.comment == comment)
        )
    finally:
        db.close()
    assert first["orders"] == 1
    assert first["duplicates"] >= 1
    assert second["orders"] == 0
    assert second["duplicates"] >= 1
    assert count == 1
