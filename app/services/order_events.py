from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import OrderEvent, OrderLine, PaymentType, ServiceOrder, User
from app.services.audit import diff_text
from app.services.cash_book import ZERO, money

ORDER_EVENT_ACTIONS = ("created", "status", "paid", "reopened", "edited", "deleted")


def order_snapshot(order: ServiceOrder | None, lines: list[OrderLine] | None = None) -> dict:
    src = lines if lines is not None else (list(order.lines) if order else [])
    gel = sum((line.client_amount for line in src), ZERO)
    eur = sum((line.warranty_eur or ZERO for line in src), ZERO)
    methods: list[str] = []
    for line in src:
        value = line.payment_type.value
        if line.payment_type != PaymentType.expense and value not in methods:
            methods.append(value)
    return {
        "status": order.status.value if order else "",
        "gel": money(gel),
        "eur": money(eur),
        "methods": ",".join(methods),
        "lines": len(src),
        "assignee": order.assignee_id if order else "",
        "center": order.service_center_id if order else "",
    }


def log_order_event(
    db: Session,
    user: User | None,
    order: ServiceOrder,
    action: str,
    details: str = "",
) -> None:
    db.add(
        OrderEvent(
            order_id=order.id,
            service_center_id=order.service_center_id,
            user_id=user.id if user else None,
            action=action,
            details=(details or "")[:4000],
        )
    )


def snapshot_diff(before: dict, after: dict) -> str:
    return diff_text(before, after)


def snapshot_text(snap: dict) -> str:
    return "; ".join(f"{key}: {value}" for key, value in snap.items())


def recent_order_events(
    db: Session,
    *,
    order_id: int | None = None,
    center_id: int | None = None,
    action: str = "",
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 200,
) -> list[OrderEvent]:
    stmt = (
        select(OrderEvent)
        .options(joinedload(OrderEvent.user))
        .order_by(OrderEvent.created_at.desc(), OrderEvent.id.desc())
        .limit(limit)
    )
    if order_id:
        stmt = stmt.where(OrderEvent.order_id == order_id)
    if center_id:
        stmt = stmt.where(OrderEvent.service_center_id == center_id)
    if action:
        stmt = stmt.where(OrderEvent.action == action)
    if date_from:
        stmt = stmt.where(OrderEvent.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        stmt = stmt.where(OrderEvent.created_at < datetime.combine(date_to + timedelta(days=1), time.min))
    return list(db.scalars(stmt).unique())
