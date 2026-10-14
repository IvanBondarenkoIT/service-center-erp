from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_admin, require_admin_screen
from app.models import Client, ClientMachine, IssueReason, Machine, ServiceOrder, User
from app.services.audit import diff_text, log_action
from app.services.erp_clients import count_cached_clients
from app.services.erp_sync import (
    count_cached_goods,
    get_sync_status,
    search_cached_goods,
    sync_erp_catalog,
)
from app.services.phones import normalize_phone
from app.templating import templates

router = APIRouter(prefix="/dict", tags=["dictionaries"])


def _order_counts(db: Session, column) -> dict[int, int]:
    rows = db.execute(
        select(column, func.count(ServiceOrder.id)).where(column.is_not(None)).group_by(column)
    )
    return {row[0]: row[1] for row in rows}


@router.get("/clients", response_class=HTMLResponse)
def clients_list(
    request: Request,
    q: str = Query(""),
    error: str = Query(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    stmt = select(Client).order_by(Client.name)
    clients = list(db.scalars(stmt))
    if q.strip():
        needle = q.strip().lower()
        clients = [
            c
            for c in clients
            if needle in c.phone.lower() or needle in (c.name or "").lower()
        ]
    return templates.TemplateResponse(
        request,
        "dictionaries/clients.html",
        {
            "user": user,
            "clients": clients,
            "q": q,
            "error": error,
            "order_counts": _order_counts(db, ServiceOrder.client_id),
        },
    )


@router.post("/clients/{client_id}/edit")
def client_update(
    client_id: int,
    name: str = Form(""),
    phone: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(404)
    phone_n = normalize_phone(phone)
    if not phone_n:
        return RedirectResponse("/dict/clients?error=admin.err_phone", status_code=303)
    other = db.scalar(select(Client).where(Client.phone == phone_n, Client.id != client.id))
    if other:
        return RedirectResponse("/dict/clients?error=admin.err_phone_taken", status_code=303)
    before = {"name": client.name, "phone": client.phone}
    client.name = name.strip() or phone_n
    client.phone = phone_n
    details = diff_text(before, {"name": client.name, "phone": client.phone})
    if details:
        log_action(db, user, "edit", "client", client.id, details)
    db.commit()
    return RedirectResponse("/dict/clients", status_code=303)


@router.post("/clients/{client_id}/delete")
def client_delete(
    client_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(404)
    if db.scalar(select(func.count(ServiceOrder.id)).where(ServiceOrder.client_id == client.id)):
        return RedirectResponse("/dict/clients?error=admin.err_in_use", status_code=303)
    details = f"{client.name}; {client.phone}"
    db.execute(delete(ClientMachine).where(ClientMachine.client_id == client.id))
    db.delete(client)
    log_action(db, user, "delete", "client", client_id, details)
    db.commit()
    return RedirectResponse("/dict/clients", status_code=303)


@router.post("/clients")
def clients_create(
    name: str = Form(""),
    phone: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    phone_n = normalize_phone(phone)
    if not phone_n:
        return RedirectResponse("/dict/clients", status_code=303)
    existing = db.scalar(select(Client).where(Client.phone == phone_n))
    if existing:
        if name:
            existing.name = name
    else:
        db.add(Client(phone=phone_n, name=name or phone_n))
    db.commit()
    return RedirectResponse("/dict/clients", status_code=303)


@router.get("/machines", response_class=HTMLResponse)
def machines_list(
    request: Request,
    q: str = Query(""),
    error: str = Query(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    stmt = select(Machine).order_by(Machine.serial_number)
    machines = list(db.scalars(stmt))
    if q.strip():
        needle = q.strip().lower()
        machines = [
            m
            for m in machines
            if needle in m.serial_number.lower() or needle in (m.model_name or "").lower()
        ]
    return templates.TemplateResponse(
        request,
        "dictionaries/machines.html",
        {
            "user": user,
            "machines": machines,
            "q": q,
            "error": error,
            "order_counts": _order_counts(db, ServiceOrder.machine_id),
        },
    )


@router.post("/machines/{machine_id}/edit")
def machine_update(
    machine_id: int,
    serial_number: str = Form(...),
    model_name: str = Form(""),
    erp_goods_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    machine = db.get(Machine, machine_id)
    if not machine:
        raise HTTPException(404)
    serial = serial_number.strip()
    if not serial:
        return RedirectResponse("/dict/machines?error=admin.err_serial", status_code=303)
    other = db.scalar(
        select(Machine).where(Machine.serial_number == serial, Machine.id != machine.id)
    )
    if other:
        return RedirectResponse("/dict/machines?error=admin.err_serial_taken", status_code=303)
    erp_raw = erp_goods_id.strip()
    before = {
        "serial": machine.serial_number,
        "model": machine.model_name,
        "erp_id": machine.erp_goods_id,
    }
    machine.serial_number = serial
    machine.model_name = model_name.strip()
    machine.erp_goods_id = int(erp_raw) if erp_raw.isdigit() else None
    machine.needs_serial = serial.startswith("NEED-SERIAL-")
    details = diff_text(
        before,
        {"serial": machine.serial_number, "model": machine.model_name, "erp_id": machine.erp_goods_id},
    )
    if details:
        log_action(db, user, "edit", "machine", machine.id, details)
    db.commit()
    return RedirectResponse("/dict/machines", status_code=303)


@router.post("/machines/{machine_id}/delete")
def machine_delete(
    machine_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    machine = db.get(Machine, machine_id)
    if not machine:
        raise HTTPException(404)
    if db.scalar(select(func.count(ServiceOrder.id)).where(ServiceOrder.machine_id == machine.id)):
        return RedirectResponse("/dict/machines?error=admin.err_in_use", status_code=303)
    details = f"{machine.serial_number}; {machine.model_name}"
    db.execute(delete(ClientMachine).where(ClientMachine.machine_id == machine.id))
    db.delete(machine)
    log_action(db, user, "delete", "machine", machine_id, details)
    db.commit()
    return RedirectResponse("/dict/machines", status_code=303)


@router.post("/machines")
def machines_create(
    serial_number: str = Form(...),
    model_name: str = Form(""),
    erp_goods_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    serial = serial_number.strip()
    if not serial:
        return RedirectResponse("/dict/machines", status_code=303)
    existing = db.scalar(select(Machine).where(Machine.serial_number == serial))
    erp_id = int(erp_goods_id) if erp_goods_id.isdigit() else None
    if existing:
        existing.model_name = model_name or existing.model_name
        if erp_id:
            existing.erp_goods_id = erp_id
        existing.needs_serial = serial.startswith("NEED-SERIAL-")
    else:
        db.add(
            Machine(
                serial_number=serial,
                model_name=model_name,
                erp_goods_id=erp_id,
                needs_serial=serial.startswith("NEED-SERIAL-"),
            )
        )
    db.commit()
    return RedirectResponse("/dict/machines", status_code=303)


@router.get("/reasons", response_class=HTMLResponse)
def reasons_list(
    request: Request,
    error: str = Query(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    reasons = list(db.scalars(select(IssueReason).order_by(IssueReason.name)))
    return templates.TemplateResponse(
        request,
        "dictionaries/reasons.html",
        {
            "user": user,
            "reasons": reasons,
            "error": error,
            "order_counts": _order_counts(db, ServiceOrder.issue_reason_id),
        },
    )


@router.post("/reasons/{reason_id}/edit")
def reason_update(
    reason_id: int,
    name: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    reason = db.get(IssueReason, reason_id)
    if not reason:
        raise HTTPException(404)
    name = name.strip()
    if not name:
        return RedirectResponse("/dict/reasons", status_code=303)
    other = db.scalar(
        select(IssueReason).where(IssueReason.name == name, IssueReason.id != reason.id)
    )
    if other:
        return RedirectResponse("/dict/reasons?error=admin.err_reason_taken", status_code=303)
    if reason.name != name:
        log_action(db, user, "edit", "reason", reason.id, f"{reason.name} → {name}")
        reason.name = name
    db.commit()
    return RedirectResponse("/dict/reasons", status_code=303)


@router.post("/reasons/{reason_id}/delete")
def reason_delete(
    reason_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    reason = db.get(IssueReason, reason_id)
    if not reason:
        raise HTTPException(404)
    if db.scalar(
        select(func.count(ServiceOrder.id)).where(ServiceOrder.issue_reason_id == reason.id)
    ):
        return RedirectResponse("/dict/reasons?error=admin.err_in_use", status_code=303)
    name = reason.name
    db.delete(reason)
    log_action(db, user, "delete", "reason", reason_id, name)
    db.commit()
    return RedirectResponse("/dict/reasons", status_code=303)


@router.post("/reasons")
def reasons_create(
    name: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    name = name.strip()
    if name and not db.scalar(select(IssueReason).where(IssueReason.name == name)):
        db.add(IssueReason(name=name))
        db.commit()
    return RedirectResponse("/dict/reasons", status_code=303)


@router.get("/erp-catalog", response_class=HTMLResponse)
def erp_catalog(
    request: Request,
    q: str = Query(""),
    kind: str = Query("machine"),
    sync_msg: str = Query(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    items = search_cached_goods(db, q, kind=kind or None, limit=100)
    sync_status = get_sync_status(db)
    return templates.TemplateResponse(
        request,
        "dictionaries/erp_catalog.html",
        {
            "user": user,
            "items": items,
            "q": q,
            "kind": kind,
            "sync_status": sync_status,
            "sync_msg": sync_msg,
            "cache_count_machines": count_cached_goods(db, "machine"),
            "cache_count_parts": count_cached_goods(db, "part"),
            "cache_count_clients": count_cached_clients(db),
        },
    )


@router.post("/erp-catalog/sync")
def erp_catalog_sync(
    mode: str = Form("incremental"),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    if mode not in ("incremental", "full"):
        mode = "incremental"
    result = sync_erp_catalog(db, mode=mode)  # type: ignore[arg-type]
    if result.get("skipped"):
        msg = result.get("reason", "skipped")
    else:
        t = result.get("totals", {})
        msg = f"ok+{t.get('added',0)}+{t.get('updated',0)}+{t.get('unchanged',0)}"
        if t.get("has_more"):
            msg += "+more"
    return RedirectResponse(f"/dict/erp-catalog?sync_msg={msg}", status_code=303)


@router.get("/erp-suggest", response_class=HTMLResponse)
def erp_suggest(
    request: Request,
    q: str = Query(""),
    kind: str = Query("machine"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items = search_cached_goods(db, q, kind=kind, limit=20)
    return templates.TemplateResponse(
        request,
        "partials/erp_suggest.html",
        {"user": user, "items": items, "q": q},
    )


@router.get("/part-suggest", response_class=HTMLResponse)
def part_suggest(
    request: Request,
    description: str = Query(""),
    line_type: str = Query(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = description.strip()
    items = []
    if line_type == "part" and len(q) >= 2:
        items = search_cached_goods(db, q, kind="part", limit=15)
    return templates.TemplateResponse(
        request,
        "partials/part_suggest.html",
        {"user": user, "items": items},
    )
