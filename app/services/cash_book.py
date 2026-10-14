from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    CashEntry,
    CashEntryKind,
    CashOpening,
    OrderLine,
    OrderStatus,
    PaymentType,
    ServiceCenter,
    ServiceOrder,
)

BUSINESS_TZ = timezone(timedelta(hours=4))  # Georgia (no DST)


def business_today() -> date:
    return datetime.now(BUSINESS_TZ).date()


def as_business_date(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(BUSINESS_TZ).date()
    if isinstance(value, date):
        return value
    return None


def cash_entry_key(
    center_id: int,
    entry_date: date,
    kind: CashEntryKind,
    amount: Decimal | int | str | None,
    description: str | None,
) -> tuple:
    return (
        center_id,
        entry_date,
        kind.value if isinstance(kind, CashEntryKind) else str(kind),
        money(amount),
        (description or "").strip(),
    )


def existing_cash_entry(
    db: Session,
    *,
    center_id: int,
    entry_date: date,
    kind: CashEntryKind,
    amount: Decimal | int | str | None,
    description: str | None,
) -> CashEntry | None:
    key = cash_entry_key(center_id, entry_date, kind, amount, description)
    return db.scalar(
        select(CashEntry).where(
            CashEntry.service_center_id == key[0],
            CashEntry.entry_date == key[1],
            CashEntry.kind == kind,
            CashEntry.amount == key[3],
            CashEntry.description == key[4],
        )
    )

ZERO = Decimal("0.00")
CENTS = Decimal("0.01")


def money(value: Decimal | int | str | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENTS)


# Turnover (вал). A new client payment method is one more entry here.
VAL_METHODS = (
    PaymentType.cash,
    PaymentType.card,
    PaymentType.transfer,
    PaymentType.promo,
)


@dataclass
class IncomeRow:
    order_id: int
    order_date: date
    payment_type: PaymentType
    amount: Decimal
    assignee: str
    note: str


@dataclass
class OutflowRow:
    entry_id: int
    entry_date: date
    amount: Decimal
    description: str
    subtype: str | None = None
    center_name: str = ""


@dataclass
class CashReport:
    date_from: date
    date_to: date
    center_id: int | None
    opening: Decimal = ZERO
    cash_in: Decimal = ZERO
    card_in: Decimal = ZERO
    transfer_in: Decimal = ZERO
    promo_in: Decimal = ZERO
    expense: Decimal = ZERO
    collection: Decimal = ZERO
    by_method: dict[str, Decimal] = field(default_factory=dict)
    income_rows: list[IncomeRow] = field(default_factory=list)
    expense_rows: list[OutflowRow] = field(default_factory=list)
    collection_rows: list[OutflowRow] = field(default_factory=list)

    @property
    def outflow(self) -> Decimal:
        return money(self.expense + self.collection)

    @property
    def closing(self) -> Decimal:
        return money(self.opening + self.cash_in - self.expense - self.collection)

    @property
    def val_rows(self) -> list[tuple[str, Decimal]]:
        return [
            (method.value, money(self.by_method.get(method.value, ZERO)))
            for method in VAL_METHODS
        ]

    @property
    def val(self) -> Decimal:
        return money(sum((amount for _, amount in self.val_rows), ZERO))


def _center_ids(db: Session, center_id: int | None) -> list[int]:
    if center_id:
        return [center_id]
    return list(db.scalars(select(ServiceCenter.id).order_by(ServiceCenter.id)))


def opening_balance(db: Session, center_ids: list[int], as_of: date) -> Decimal:
    total = ZERO
    for cid in center_ids:
        row = db.scalar(
            select(CashOpening)
            .where(
                CashOpening.service_center_id == cid,
                CashOpening.as_of_date <= as_of,
            )
            .order_by(CashOpening.as_of_date.desc())
            .limit(1)
        )
        if row:
            total += money(row.amount)
    return money(total)


def _cash_date(order: ServiceOrder) -> date:
    paid = as_business_date(order.paid_at)
    if paid is not None:
        return paid
    return order.order_date


def _in_cash_period(order: ServiceOrder, date_from: date, date_to: date) -> bool:
    """Till day is pay time (Tbilisi); also keep the order_date so a same-day job is not dropped."""
    paid = as_business_date(order.paid_at)
    if paid is not None and date_from <= paid <= date_to:
        return True
    return date_from <= order.order_date <= date_to


def build_cash_report(
    db: Session,
    date_from: date,
    date_to: date,
    center_id: int | None = None,
) -> CashReport:
    ids = _center_ids(db, center_id)
    report = CashReport(
        date_from=date_from,
        date_to=date_to,
        center_id=center_id,
        opening=opening_balance(db, ids, date_from),
    )
    if not ids:
        return report

    orders = list(
        db.scalars(
            select(ServiceOrder)
            .options(
                joinedload(ServiceOrder.lines),
                joinedload(ServiceOrder.assignee),
                joinedload(ServiceOrder.machine),
                joinedload(ServiceOrder.service_center),
            )
            .where(
                ServiceOrder.status == OrderStatus.issued,
                ServiceOrder.service_center_id.in_(ids),
            )
            .order_by(ServiceOrder.order_date, ServiceOrder.id)
        ).unique()
    )
    for order in orders:
        if not _in_cash_period(order, date_from, date_to):
            continue
        cash_date = _cash_date(order)
        if cash_date < date_from or cash_date > date_to:
            cash_date = order.order_date
        buckets = {method.value: ZERO for method in VAL_METHODS}
        for line in order.lines:
            if line.payment_type not in VAL_METHODS:
                continue
            buckets[line.payment_type.value] += money(line.amount_work) + money(line.amount_parts)
        if all(amount == ZERO for amount in buckets.values()):
            continue
        assignee = (
            (order.assignee.full_name or order.assignee.login) if order.assignee else ""
        )
        note = (order.machine.serial_number if order.machine else "") or f"#{order.id}"
        for method in VAL_METHODS:
            amount = money(buckets[method.value])
            if amount == ZERO:
                continue
            report.by_method[method.value] = money(
                report.by_method.get(method.value, ZERO) + amount
            )
            report.income_rows.append(
                IncomeRow(
                    order_id=order.id,
                    order_date=cash_date,
                    payment_type=method,
                    amount=amount,
                    assignee=assignee,
                    note=note,
                )
            )
    report.cash_in = money(report.by_method.get(PaymentType.cash.value, ZERO))
    report.card_in = money(report.by_method.get(PaymentType.card.value, ZERO))
    report.transfer_in = money(report.by_method.get(PaymentType.transfer.value, ZERO))
    report.promo_in = money(report.by_method.get(PaymentType.promo.value, ZERO))
    for method in VAL_METHODS:
        report.by_method.setdefault(method.value, ZERO)

    entries = list(
        db.scalars(
            select(CashEntry)
            .options(joinedload(CashEntry.service_center))
            .where(
                CashEntry.entry_date >= date_from,
                CashEntry.entry_date <= date_to,
                CashEntry.service_center_id.in_(ids),
            )
            .order_by(CashEntry.entry_date, CashEntry.id)
        )
    )
    for entry in entries:
        row = OutflowRow(
            entry_id=entry.id,
            entry_date=entry.entry_date,
            amount=money(entry.amount),
            description=entry.description,
            subtype=entry.subtype.value if entry.subtype else None,
            center_name=entry.service_center.name if entry.service_center else "",
        )
        if entry.kind == CashEntryKind.expense:
            report.expense += row.amount
            report.expense_rows.append(row)
        elif entry.kind == CashEntryKind.collection:
            report.collection += row.amount
            report.collection_rows.append(row)
    report.expense = money(report.expense)
    report.collection = money(report.collection)
    return report


def recent_cash_entries(
    db: Session, center_id: int | None = None, limit: int = 30
) -> list[CashEntry]:
    stmt = (
        select(CashEntry)
        .options(joinedload(CashEntry.service_center))
        .order_by(CashEntry.entry_date.desc(), CashEntry.id.desc())
        .limit(limit)
    )
    if center_id:
        stmt = stmt.where(CashEntry.service_center_id == center_id)
    return list(db.scalars(stmt).unique())


def cash_report_xlsx(report: CashReport) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Cash"
    period = f"{report.date_from.isoformat()} — {report.date_to.isoformat()}"
    ws["A1"] = f"Period {period}"
    ws["A2"] = "Opening"
    ws["B2"] = float(report.opening)
    ws["A3"] = "Cash in"
    ws["B3"] = float(report.cash_in)
    ws["A4"] = "Terminal"
    ws["B4"] = float(report.card_in)
    ws["A5"] = "Expense"
    ws["B5"] = float(report.expense)
    ws["A6"] = "Collection"
    ws["B6"] = float(report.collection)
    ws["A7"] = "Closing"
    ws["B7"] = float(report.closing)
    ws["A8"] = (
        "opening + cash - expense - collection (terminal, transfer and promo not in till)"
    )
    ws["A9"] = "Transfer"
    ws["B9"] = float(report.transfer_in)
    excel_labels = {
        PaymentType.cash.value: "Cash",
        PaymentType.card.value: "Terminal",
        PaymentType.transfer.value: "Transfer",
        PaymentType.promo.value: "Promo",
    }
    row_no = 11
    ws.cell(row_no, 1, "Val")
    row_no += 1
    for method_value, amount in report.val_rows:
        ws.cell(row_no, 1, excel_labels.get(method_value, method_value))
        ws.cell(row_no, 2, float(amount))
        row_no += 1
    ws.cell(row_no, 1, "Val total")
    ws.cell(row_no, 2, float(report.val))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
