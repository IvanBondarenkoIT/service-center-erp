from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import func, select

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


def test_excel_import_marks_orders_issued(tmp_path) -> None:
    comment = f"imported-history-{uuid.uuid4().hex[:8]}"
    path = tmp_path / "orders.xlsx"
    _write_sample(path, comment)
    db = SessionLocal()
    try:
        stats = import_excel(db, path, default_center_code="batumi")
        order = db.scalar(select(ServiceOrder).where(ServiceOrder.comment == comment))
    finally:
        db.close()
    assert stats["orders"] == 1
    assert order is not None
    assert order.status == OrderStatus.issued


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
