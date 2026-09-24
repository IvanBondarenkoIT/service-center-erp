from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import get_staff_user
from app.models import (
    Client,
    ClientMachine,
    IssueReason,
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
from app.services.phones import normalize_phone
from app.services.cash_book import BUSINESS_TZ
from app.services.serial_scan import serial_from_scan
from app.templating import templates

router = APIRouter(tags=["orders"])

WORKFLOW_STATUSES = (
    OrderStatus.in_progress,
    OrderStatus.waiting_part,
    OrderStatus.ready,
)
PAY_METHODS = (PaymentType.cash, PaymentType.card)
FORM_LINE_TYPES = (LineType.work, LineType.part, LineType.diagnostic)


def _scoped_orders_query(user: User):
    stmt = (
        select(ServiceOrder)
        .options(
            joinedload(ServiceOrder.machine),
            joinedload(ServiceOrder.client),
            joinedload(ServiceOrder.service_center),
            joinedload(ServiceOrder.assignee),
            joinedload(ServiceOrder.lines),
        )
        .order_by(ServiceOrder.order_date.desc(), ServiceOrder.id.desc())
    )
    if user.role != UserRole.admin:
        stmt = stmt.where(ServiceOrder.assignee_id == user.id)
    return stmt


def _parse_decimal(raw: str | None) -> Decimal:
    if not raw:
        return Decimal("0")
    try:
        return Decimal(str(raw).replace(",", ".").strip() or "0")
    except InvalidOperation:
        return Decimal("0")


def _ensure_client(db: Session, phone: str, name: str) -> Client | None:
    phone_n = normalize_phone(phone)
    if not phone_n and not name:
        return None
    if not phone_n:
        phone_n = f"noname-{name.strip().lower()}"[:32]
    client = db.scalar(select(Client).where(Client.phone == phone_n))
    if client:
        if name and client.name != name:
            client.name = name
        return client
    client = Client(phone=phone_n, name=name or phone_n)
    db.add(client)
    db.flush()
    return client


def _ensure_machine(
    db: Session,
    serial: str,
    model_name: str,
    erp_goods_id: int | None = None,
) -> Machine:
    serial = (serial or "").strip()
    if not serial:
        raise HTTPException(status_code=400, detail="sn_required")
    machine = db.scalar(select(Machine).where(Machine.serial_number == serial))
    if machine:
        if model_name:
            machine.model_name = model_name
        if erp_goods_id:
            machine.erp_goods_id = erp_goods_id
        if not serial.startswith("NEED-SERIAL-"):
            machine.needs_serial = False
        return machine
    machine = Machine(
        serial_number=serial,
        model_name=model_name or "",
        erp_goods_id=erp_goods_id,
        needs_serial=serial.startswith("NEED-SERIAL-"),
    )
    db.add(machine)
    db.flush()
    return machine


def _link_client_machine(db: Session, client: Client | None, machine: Machine) -> None:
    if not client:
        return
    exists = db.scalar(
        select(ClientMachine).where(
            ClientMachine.client_id == client.id,
            ClientMachine.machine_id == machine.id,
        )
    )
    if not exists:
        db.add(ClientMachine(client_id=client.id, machine_id=machine.id))


def _parse_lines_from_form(
    line_type: list[str],
    description: list[str],
    part_code: list[str],
    payment_type: list[str],
    amount: list[str],
    is_warranty: list[str],
    amount_work: list[str] | None = None,
    amount_parts: list[str] | None = None,
) -> list[OrderLine]:
    lines: list[OrderLine] = []
    amount_work = amount_work or []
    amount_parts = amount_parts or []
    n = max(len(line_type), len(description), len(amount), 1)

    def pad(xs: list[str], size: int) -> list[str]:
        return list(xs) + [""] * (size - len(xs))

    line_type = pad(line_type, n)
    description = pad(description, n)
    part_code = pad(part_code, n)
    payment_type = pad(payment_type, n)
    amount = pad(amount, n)
    is_warranty = pad(is_warranty, n)
    amount_work = pad(amount_work, n)
    amount_parts = pad(amount_parts, n)

    for i in range(n):
        desc = (description[i] or "").strip()
        pc = (part_code[i] or "").strip()
        try:
            lt = LineType(line_type[i])
        except ValueError:
            lt = LineType.work

        warranty_flag = str(is_warranty[i] or "").strip().lower() in {
            "1",
            "true",
            "on",
            "yes",
            "garanty",
            "warranty",
        }
        try:
            pt = PaymentType(payment_type[i])
        except ValueError:
            pt = PaymentType.cash

        if lt == LineType.warranty or pt == PaymentType.warranty:
            warranty_flag = True
            if lt == LineType.warranty:
                lt = LineType.work

        if lt == LineType.expense:
            # Legacy rows only — keep both amount columns as submitted.
            aw = _parse_decimal(amount_work[i] or amount[i])
            ap = _parse_decimal(amount_parts[i])
            if amount[i] and not amount_work[i] and not amount_parts[i]:
                aw = _parse_decimal(amount[i])
                ap = Decimal("0")
            if not desc and not pc and aw == 0 and ap == 0:
                continue
            lines.append(
                OrderLine(
                    line_type=LineType.expense,
                    description=desc,
                    part_code=pc,
                    payment_type=PaymentType.expense,
                    amount_work=aw,
                    amount_parts=ap,
                )
            )
            continue

        if lt not in FORM_LINE_TYPES:
            lt = LineType.work

        if amount[i] not in ("", None):
            total = _parse_decimal(amount[i])
        else:
            total = _parse_decimal(amount_work[i]) + _parse_decimal(amount_parts[i])

        if warranty_flag:
            total = Decimal("0")
            pt = PaymentType.warranty
            aw, ap = Decimal("0"), Decimal("0")
        elif lt == LineType.part:
            aw, ap = Decimal("0"), total
            if pt == PaymentType.warranty:
                pt = PaymentType.cash
        else:
            aw, ap = total, Decimal("0")
            if pt == PaymentType.warranty:
                pt = PaymentType.cash

        if not desc and not pc and aw == 0 and ap == 0 and not warranty_flag:
            continue
        lines.append(
            OrderLine(
                line_type=lt,
                description=desc,
                part_code=pc,
                payment_type=pt,
                amount_work=aw,
                amount_parts=ap,
            )
        )
    if not lines:
        lines.append(
            OrderLine(
                line_type=LineType.work,
                description="",
                payment_type=PaymentType.cash,
                amount_work=Decimal("0"),
                amount_parts=Decimal("0"),
            )
        )
    return lines


@router.get("/", response_class=HTMLResponse)
def orders_list(
    request: Request,
    q: str = Query(""),
    status: str = Query(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_staff_user),
):
    stmt = _scoped_orders_query(user)
    status_filter = status.strip()
    if status_filter:
        try:
            stmt = stmt.where(ServiceOrder.status == OrderStatus(status_filter))
        except ValueError:
            status_filter = ""
    orders = list(db.scalars(stmt).unique())
    if q.strip():
        needle = q.strip().lower()
        orders = [
            o
            for o in orders
            if needle in (o.machine.serial_number or "").lower()
            or needle in (o.machine.model_name or "").lower()
            or needle in (o.client.phone if o.client else "")
            or needle in (o.client.name if o.client else "").lower()
            or needle in (o.comment or "").lower()
        ]
    return templates.TemplateResponse(
        request,
        "orders/list.html",
        {
            "user": user,
            "orders": orders,
            "q": q,
            "status": status_filter,
            "statuses": list(OrderStatus),
        },
    )


@router.get("/orders/new", response_class=HTMLResponse)
def order_new(
    request: Request,
    user: User = Depends(get_staff_user),
):
    return RedirectResponse("/orders/intake", status_code=303)


@router.get("/orders/intake", response_class=HTMLResponse)
def order_intake_form(
    request: Request,
    user: User = Depends(get_staff_user),
):
    return templates.TemplateResponse(
        request,
        "orders/intake.html",
        {
            "user": user,
            "error": "",
            "phone": "",
            "name": "",
            "serial": "",
        },
    )


@router.post("/orders/intake")
async def order_intake_submit(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_staff_user),
):
    form = await request.form()
    serial = serial_from_scan(str(form.get("new_machine_serial") or ""))
    phone = str(form.get("new_client_phone") or "").strip()
    name = str(form.get("new_client_name") or "").strip()
    phone_n = normalize_phone(phone)

    def fail(code: str):
        return templates.TemplateResponse(
            request,
            "orders/intake.html",
            {
                "user": user,
                "error": code,
                "phone": phone,
                "name": name,
                "serial": serial,
            },
            status_code=400,
        )

    if not serial:
        return fail("sn_required")
    if not phone_n:
        return fail("phone_required")

    assignee_id = user.id
    service_center_id = user.service_center_id or 0
    if user.role == UserRole.admin:
        assignee_id = int(form.get("assignee_id") or user.id)
        service_center_id = int(form.get("service_center_id") or service_center_id or 0)
    if not service_center_id:
        center = db.scalar(select(ServiceCenter).order_by(ServiceCenter.id).limit(1))
        if not center:
            raise HTTPException(400, "no_center")
        service_center_id = center.id

    machine = _ensure_machine(db, serial, "", None)
    client = _ensure_client(db, phone, name)
    _link_client_machine(db, client, machine)

    order = ServiceOrder(
        order_date=date.today(),
        assignee_id=assignee_id,
        service_center_id=service_center_id,
        machine_id=machine.id,
        client_id=client.id if client else None,
        comment="",
        status=OrderStatus.in_progress,
        lines=[
            OrderLine(
                line_type=LineType.work,
                description="",
                payment_type=PaymentType.cash,
                amount_work=Decimal("0"),
                amount_parts=Decimal("0"),
            )
        ],
    )
    db.add(order)
    db.commit()
    return RedirectResponse(f"/orders/{order.id}", status_code=303)


@router.get("/orders/{order_id}", response_class=HTMLResponse)
def order_edit(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_staff_user),
):
    order = db.scalar(
        select(ServiceOrder)
        .options(
            joinedload(ServiceOrder.lines),
            joinedload(ServiceOrder.machine),
            joinedload(ServiceOrder.client),
        )
        .where(ServiceOrder.id == order_id)
    )
    if not order:
        raise HTTPException(404)
    if user.role != UserRole.admin and order.assignee_id != user.id:
        raise HTTPException(403)
    return _order_form(request, db, user, order=order)


def _order_form(request: Request, db: Session, user: User, order: ServiceOrder | None):
    centers = list(db.scalars(select(ServiceCenter).order_by(ServiceCenter.id)))
    reasons = list(db.scalars(select(IssueReason).order_by(IssueReason.name)))
    mechanics = list(
        db.scalars(select(User).where(User.role == UserRole.mechanic).order_by(User.login))
    )
    history = []
    if order and order.machine and not order.machine.needs_serial:
        history = _machine_history(db, order.machine.id, exclude_order_id=order.id)
    return templates.TemplateResponse(
        request,
        "orders/form.html",
        {
            "user": user,
            "order": order,
            "centers": centers,
            "reasons": reasons,
            "mechanics": mechanics,
            "line_types": list(FORM_LINE_TYPES),
            "pay_methods": list(PAY_METHODS),
            "statuses": list(WORKFLOW_STATUSES),
            "history": history,
            "today": date.today().isoformat(),
            "locked": bool(
                order
                and order.status == OrderStatus.issued
                and user.role != UserRole.admin
            ),
        },
    )


def _machine_history(db: Session, machine_id: int, exclude_order_id: int | None = None):
    stmt = (
        select(ServiceOrder)
        .options(
            joinedload(ServiceOrder.assignee),
            joinedload(ServiceOrder.service_center),
            joinedload(ServiceOrder.lines),
            joinedload(ServiceOrder.issue_reason),
        )
        .where(ServiceOrder.machine_id == machine_id)
        .order_by(ServiceOrder.order_date.desc(), ServiceOrder.id.desc())
    )
    if exclude_order_id:
        stmt = stmt.where(ServiceOrder.id != exclude_order_id)
    return list(db.scalars(stmt).unique())


@router.post("/orders/save")
async def order_save(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_staff_user),
):
    form = await request.form()
    order_id_raw = form.get("order_id")
    order_id = int(order_id_raw) if order_id_raw else None

    order_date_raw = str(form.get("order_date") or "")
    try:
        order_date = date.fromisoformat(order_date_raw)
    except ValueError:
        order_date = date.today()

    comment = str(form.get("comment") or "")
    status_raw = str(form.get("status") or OrderStatus.in_progress.value)
    try:
        status = OrderStatus(status_raw)
    except ValueError:
        status = OrderStatus.in_progress
    if status == OrderStatus.issued or status not in WORKFLOW_STATUSES:
        status = OrderStatus.in_progress
    service_center_id = int(form.get("service_center_id") or 0)
    assignee_id = int(form.get("assignee_id") or user.id)
    if user.role != UserRole.admin:
        assignee_id = user.id
        if user.service_center_id:
            service_center_id = user.service_center_id

    # Machine: existing id or create
    machine_id_raw = str(form.get("machine_id") or "").strip()
    new_serial = str(form.get("new_machine_serial") or "").strip()
    new_model = str(form.get("new_machine_model") or "").strip()
    erp_goods_id_raw = str(form.get("erp_goods_id") or "").strip()
    erp_goods_id = int(erp_goods_id_raw) if erp_goods_id_raw.isdigit() else None

    if new_serial:
        machine = _ensure_machine(db, new_serial, new_model, erp_goods_id)
    elif machine_id_raw.isdigit():
        machine = db.get(Machine, int(machine_id_raw))
        if not machine:
            raise HTTPException(400, "Кофеварка не найдена")
        if new_model:
            machine.model_name = new_model
    else:
        raise HTTPException(400, "sn_required")

    # Client
    client_id_raw = str(form.get("client_id") or "").strip()
    new_phone = str(form.get("new_client_phone") or "").strip()
    new_name = str(form.get("new_client_name") or "").strip()
    client = None
    if new_phone or new_name:
        client = _ensure_client(db, new_phone, new_name)
    elif client_id_raw.isdigit():
        client = db.get(Client, int(client_id_raw))

    _link_client_machine(db, client, machine)

    reason_id_raw = str(form.get("issue_reason_id") or "").strip()
    new_reason = str(form.get("new_issue_reason") or "").strip()
    issue_reason_id = None
    if new_reason:
        existing = db.scalar(select(IssueReason).where(IssueReason.name == new_reason))
        if existing:
            issue_reason_id = existing.id
        else:
            reason = IssueReason(name=new_reason)
            db.add(reason)
            db.flush()
            issue_reason_id = reason.id
    elif reason_id_raw.isdigit():
        issue_reason_id = int(reason_id_raw)

    # Lines from repeated fields
    def getlist(key: str) -> list[str]:
        return [str(v) for v in form.getlist(key)]

    lines = _parse_lines_from_form(
        getlist("line_type"),
        getlist("description"),
        getlist("part_code"),
        getlist("payment_type"),
        getlist("amount"),
        getlist("is_warranty"),
        getlist("amount_work"),
        getlist("amount_parts"),
    )

    if order_id:
        order = db.get(ServiceOrder, order_id)
        if not order:
            raise HTTPException(404)
        if user.role != UserRole.admin and order.assignee_id != user.id:
            raise HTTPException(403)
        if order.status == OrderStatus.issued:
            if user.role != UserRole.admin:
                raise HTTPException(403)
            status = OrderStatus.issued
        order.order_date = order_date
        order.assignee_id = assignee_id
        order.service_center_id = service_center_id
        order.machine_id = machine.id
        order.client_id = client.id if client else None
        order.issue_reason_id = issue_reason_id
        order.comment = comment
        order.status = status
        order.lines.clear()
        for line in lines:
            order.lines.append(line)
    else:
        order = ServiceOrder(
            order_date=order_date,
            assignee_id=assignee_id,
            service_center_id=service_center_id,
            machine_id=machine.id,
            client_id=client.id if client else None,
            issue_reason_id=issue_reason_id,
            comment=comment,
            status=status,
            lines=lines,
        )
        db.add(order)

    db.commit()
    return RedirectResponse(f"/orders/{order.id}", status_code=303)


def _mark_paid(order: ServiceOrder, payment: PaymentType) -> None:
    for line in order.lines:
        if line.line_type == LineType.expense:
            line.payment_type = PaymentType.expense
        elif (
            line.line_type == LineType.warranty
            or line.payment_type == PaymentType.warranty
        ):
            line.payment_type = PaymentType.warranty
        else:
            line.payment_type = payment
    order.status = OrderStatus.issued
    order.paid_at = datetime.now(BUSINESS_TZ)


@router.post("/orders/{order_id}/pay")
async def order_pay(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_staff_user),
):
    order = db.scalars(
        select(ServiceOrder)
        .options(joinedload(ServiceOrder.lines))
        .where(ServiceOrder.id == order_id)
    ).unique().one_or_none()
    if not order:
        raise HTTPException(404)
    if user.role != UserRole.admin and order.assignee_id != user.id:
        raise HTTPException(403)
    if order.status == OrderStatus.issued:
        raise HTTPException(400, "already_paid")
    form = await request.form()
    raw = str(form.get("payment_type") or "")
    try:
        payment = PaymentType(raw)
    except ValueError:
        raise HTTPException(400, "payment_required")
    if payment not in PAY_METHODS:
        raise HTTPException(400, "payment_required")
    _mark_paid(order, payment)
    db.commit()
    return RedirectResponse(f"/orders/{order.id}", status_code=303)


@router.get("/orders/partials/line-row", response_class=HTMLResponse)
def line_row_partial(request: Request, user: User = Depends(get_staff_user)):
    return templates.TemplateResponse(
        request,
        "orders/_line_row.html",
        {
            "user": user,
            "line": None,
            "line_types": list(FORM_LINE_TYPES),
            "locked": False,
        },
    )


def _client_history(db: Session, phone: str, limit: int = 30) -> tuple[Client | None, list[ServiceOrder]]:
    phone_n = normalize_phone(phone)
    if not phone_n:
        return None, []
    client = db.scalar(select(Client).where(Client.phone == phone_n))
    if not client:
        return None, []
    stmt = (
        select(ServiceOrder)
        .options(
            joinedload(ServiceOrder.machine),
            joinedload(ServiceOrder.issue_reason),
            joinedload(ServiceOrder.assignee),
        )
        .where(ServiceOrder.client_id == client.id)
        .order_by(ServiceOrder.order_date.desc(), ServiceOrder.id.desc())
        .limit(limit)
    )
    return client, list(db.scalars(stmt).unique())


@router.get("/orders/partials/history", response_class=HTMLResponse)
def history_partial(
    request: Request,
    machine_id: int | None = None,
    serial: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_staff_user),
):
    machine = None
    if machine_id:
        machine = db.get(Machine, machine_id)
    elif serial.strip():
        sn = serial_from_scan(serial)
        machine = db.scalar(select(Machine).where(Machine.serial_number == sn))
    history = _machine_history(db, machine.id) if machine else []
    return templates.TemplateResponse(
        request,
        "orders/_history.html",
        {"user": user, "machine": machine, "history": history},
    )


@router.get("/orders/partials/history-by-client", response_class=HTMLResponse)
def history_by_client_partial(
    request: Request,
    phone: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_staff_user),
):
    client, history = _client_history(db, phone)
    return templates.TemplateResponse(
        request,
        "orders/_history_client.html",
        {"user": user, "client": client, "history": history, "phone": phone},
    )


@router.get("/orders/partials/suggest-link", response_class=HTMLResponse)
def suggest_link(
    request: Request,
    client_id: int | None = None,
    machine_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_staff_user),
):
    """Soft auto-fill: given client → suggest machine; given machine → suggest client."""
    suggested_client = None
    suggested_machine = None
    if client_id and not machine_id:
        link = db.scalar(
            select(ClientMachine)
            .where(ClientMachine.client_id == client_id)
            .order_by(ClientMachine.id.desc())
        )
        if link:
            suggested_machine = db.get(Machine, link.machine_id)
    if machine_id and not client_id:
        link = db.scalar(
            select(ClientMachine)
            .where(ClientMachine.machine_id == machine_id)
            .order_by(ClientMachine.id.desc())
        )
        if link:
            suggested_client = db.get(Client, link.client_id)
    return templates.TemplateResponse(
        request,
        "orders/_suggest_link.html",
        {
            "user": user,
            "suggested_client": suggested_client,
            "suggested_machine": suggested_machine,
        },
    )
