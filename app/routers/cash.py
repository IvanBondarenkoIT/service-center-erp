from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_admin, require_cash_editor
from app.models import (
    CashEntry,
    CashEntryKind,
    CollectionSubtype,
    ServiceCenter,
    User,
    UserRole,
)
from app.services.cash_book import (
    build_cash_report,
    business_today,
    cash_report_xlsx,
    existing_cash_entry,
    recent_cash_entries,
)
from app.templating import templates

router = APIRouter(tags=["cash"])


def _parse_date(raw: str, fallback: date) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return fallback


def _parse_amount(raw: str) -> Decimal:
    try:
        value = Decimal(str(raw).replace(",", ".").replace(" ", "").strip() or "0")
    except InvalidOperation:
        return Decimal("0")
    return value


def _period(date_from: str, date_to: str) -> tuple[date, date]:
    today = business_today()
    d_from = _parse_date(date_from, today.replace(day=1))
    d_to = _parse_date(date_to, today)
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    return d_from, d_to


def _report_center_id(user: User, center_id: int | None) -> int | None:
    if user.role == UserRole.mechanic:
        return user.service_center_id
    return center_id


@router.get("/cash", response_class=HTMLResponse)
def cash_report(
    request: Request,
    date_from: str = Query(""),
    date_to: str = Query(""),
    center_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    d_from, d_to = _period(date_from, date_to)
    scoped = _report_center_id(user, center_id)
    report = build_cash_report(db, d_from, d_to, scoped)
    centers = list(db.scalars(select(ServiceCenter).order_by(ServiceCenter.id)))
    return templates.TemplateResponse(
        request,
        "cash/report.html",
        {
            "user": user,
            "report": report,
            "centers": centers,
            "date_from": d_from.isoformat(),
            "date_to": d_to.isoformat(),
            "center_id": scoped,
            "can_edit": user.role != UserRole.accountant,
        },
    )


@router.get("/cash.xlsx")
def cash_report_xlsx_download(
    date_from: str = Query(""),
    date_to: str = Query(""),
    center_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    d_from, d_to = _period(date_from, date_to)
    scoped = _report_center_id(user, center_id)
    report = build_cash_report(db, d_from, d_to, scoped)
    body = cash_report_xlsx(report)
    filename = f"cash_{d_from.isoformat()}_{d_to.isoformat()}.xlsx"
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/cash/entries", response_class=HTMLResponse)
def cash_entries_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_cash_editor),
):
    centers = list(db.scalars(select(ServiceCenter).order_by(ServiceCenter.id)))
    center_id = user.service_center_id if user.role != UserRole.admin else None
    entries = recent_cash_entries(db, center_id=center_id)
    return templates.TemplateResponse(
        request,
        "cash/entries.html",
        {
            "user": user,
            "centers": centers,
            "entries": entries,
            "kinds": list(CashEntryKind),
            "subtypes": list(CollectionSubtype),
            "today": date.today().isoformat(),
        },
    )


@router.post("/cash/entries")
def cash_entries_create(
    kind: str = Form(...),
    entry_date: str = Form(...),
    amount: str = Form(...),
    description: str = Form(""),
    subtype: str = Form(""),
    service_center_id: int | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_cash_editor),
):
    try:
        entry_kind = CashEntryKind(kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bad_kind") from exc
    parsed_date = _parse_date(entry_date, date.today())
    value = _parse_amount(amount)
    if value <= 0:
        raise HTTPException(status_code=400, detail="bad_amount")

    coll_subtype = None
    if entry_kind == CashEntryKind.collection:
        try:
            coll_subtype = CollectionSubtype(subtype)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="bad_subtype") from exc

    center_id = service_center_id
    if user.role != UserRole.admin:
        if service_center_id and service_center_id != user.service_center_id:
            raise HTTPException(status_code=403, detail="Foreign service center")
        center_id = user.service_center_id
    if not center_id:
        raise HTTPException(status_code=400, detail="no_center")

    desc = (description or "").strip()
    if existing_cash_entry(
        db,
        center_id=center_id,
        entry_date=parsed_date,
        kind=entry_kind,
        amount=value,
        description=desc,
    ):
        return RedirectResponse("/cash/entries", status_code=303)

    db.add(
        CashEntry(
            entry_date=parsed_date,
            service_center_id=center_id,
            kind=entry_kind,
            subtype=coll_subtype,
            amount=value,
            description=desc,
            created_by_id=user.id,
        )
    )
    db.commit()
    return RedirectResponse("/cash/entries", status_code=303)


@router.get("/more", response_class=HTMLResponse)
def more_page(request: Request, user: User = Depends(require_admin)):
    return templates.TemplateResponse(
        request,
        "more.html",
        {"user": user},
    )
