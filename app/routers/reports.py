from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import require_admin
from app.models import Machine, ServiceCenter, ServiceOrder, User
from app.templating import templates

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", response_class=HTMLResponse)
def reports_home(
    request: Request,
    date_from: str = Query(""),
    date_to: str = Query(""),
    center_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    today = date.today()
    d_from = date.fromisoformat(date_from) if date_from else today.replace(day=1)
    d_to = date.fromisoformat(date_to) if date_to else today

    stmt = (
        select(ServiceOrder)
        .options(
            joinedload(ServiceOrder.lines),
            joinedload(ServiceOrder.service_center),
            joinedload(ServiceOrder.machine),
            joinedload(ServiceOrder.issue_reason),
        )
        .where(ServiceOrder.order_date >= d_from, ServiceOrder.order_date <= d_to)
    )
    if center_id:
        stmt = stmt.where(ServiceOrder.service_center_id == center_id)
    orders = list(db.scalars(stmt).unique())

    by_center: dict[str, Decimal] = {}
    by_payment: dict[str, Decimal] = {}
    reason_counts: dict[str, int] = {}
    total = Decimal("0")

    for order in orders:
        center_name = order.service_center.name if order.service_center else "—"
        order_sum = order.total_amount
        total += order_sum
        by_center[center_name] = by_center.get(center_name, Decimal("0")) + order_sum
        if order.issue_reason:
            reason_counts[order.issue_reason.name] = (
                reason_counts.get(order.issue_reason.name, 0) + 1
            )
        for line in order.lines:
            key = line.payment_type.value
            line_sum = (line.amount_work or 0) + (line.amount_parts or 0)
            by_payment[key] = by_payment.get(key, Decimal("0")) + Decimal(line_sum)

    # Repeat machines (serial history): count orders per machine with real serial
    machine_counts = db.execute(
        select(Machine.serial_number, Machine.model_name, func.count(ServiceOrder.id))
        .join(ServiceOrder, ServiceOrder.machine_id == Machine.id)
        .where(Machine.needs_serial.is_(False))
        .group_by(Machine.id)
        .having(func.count(ServiceOrder.id) > 1)
        .order_by(func.count(ServiceOrder.id).desc())
        .limit(30)
    ).all()

    centers = list(db.scalars(select(ServiceCenter).order_by(ServiceCenter.id)))
    top_reasons = sorted(reason_counts.items(), key=lambda x: -x[1])[:20]

    return templates.TemplateResponse(
        request,
        "reports/index.html",
        {
            "user": user,
            "date_from": d_from.isoformat(),
            "date_to": d_to.isoformat(),
            "center_id": center_id,
            "centers": centers,
            "orders_count": len(orders),
            "total": total,
            "by_center": sorted(by_center.items()),
            "by_payment": sorted(by_payment.items()),
            "top_reasons": top_reasons,
            "repeat_machines": machine_counts,
        },
    )
