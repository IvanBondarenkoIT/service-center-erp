from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_admin, require_admin_screen
from app.models import Client, IssueReason, Machine, User
from app.services.erp_sync import (
    count_cached_goods,
    get_sync_status,
    search_cached_goods,
    sync_erp_catalog,
)
from app.services.phones import normalize_phone
from app.templating import templates

router = APIRouter(prefix="/dict", tags=["dictionaries"])


@router.get("/clients", response_class=HTMLResponse)
def clients_list(
    request: Request,
    q: str = Query(""),
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
        {"user": user, "clients": clients, "q": q},
    )


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
        {"user": user, "machines": machines, "q": q},
    )


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
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    reasons = list(db.scalars(select(IssueReason).order_by(IssueReason.name)))
    return templates.TemplateResponse(
        request,
        "dictionaries/reasons.html",
        {"user": user, "reasons": reasons},
    )


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
    items = search_cached_goods(db, q, kind=kind, limit=15)
    return templates.TemplateResponse(
        request,
        "partials/erp_suggest.html",
        {"user": user, "items": items, "q": q},
    )
