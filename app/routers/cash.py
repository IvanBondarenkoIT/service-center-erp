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
    CashOpening,
    CollectionSubtype,
    PaymentType,
    ServiceCenter,
    User,
    UserRole,
)
from app.services.cash_book import (
    VAL_METHODS,
    build_cash_report,
    business_today,
    cash_report_xlsx,
    existing_cash_entry,
    lock_date,
    recent_cash_entries,
)
from app.services.audit import diff_text, log_action
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


def _pay_filter(raw: str) -> PaymentType | None:
    try:
        method = PaymentType(raw)
    except ValueError:
        return None
    return method if method in VAL_METHODS else None


@router.get("/cash", response_class=HTMLResponse)
def cash_report(
    request: Request,
    date_from: str = Query(""),
    date_to: str = Query(""),
    center_id: int | None = Query(None),
    method: str = Query(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    d_from, d_to = _period(date_from, date_to)
    scoped = _report_center_id(user, center_id)
    report = build_cash_report(db, d_from, d_to, scoped)
    pay_filter = _pay_filter(method)
    income_rows = report.income_rows
    if pay_filter:
        income_rows = [row for row in income_rows if row.amount_of(pay_filter)]
    centers = list(db.scalars(select(ServiceCenter).order_by(ServiceCenter.id)))
    return templates.TemplateResponse(
        request,
        "cash/report.html",
        {
            "user": user,
            "report": report,
            "income_rows": income_rows,
            "pay_filter": pay_filter,
            "pay_methods": VAL_METHODS,
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


def _center_locks(db: Session, centers: list[ServiceCenter]) -> dict[int, date]:
    locks = {}
    for c in centers:
        locked = lock_date(db, c.id)
        if locked:
            locks[c.id] = locked
    return locks


def _is_closed(db: Session, center_id: int, day: date) -> bool:
    locked = lock_date(db, center_id)
    return bool(locked and day < locked)


@router.get("/cash/entries", response_class=HTMLResponse)
def cash_entries_page(
    request: Request,
    error: str = Query(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_cash_editor),
):
    centers = list(db.scalars(select(ServiceCenter).order_by(ServiceCenter.id)))
    locks = _center_locks(db, centers)
    center_id = user.service_center_id if user.role != UserRole.admin else None
    entries = recent_cash_entries(db, center_id=center_id)
    openings = []
    if user.role == UserRole.admin:
        openings = list(
            db.scalars(
                select(CashOpening).order_by(
                    CashOpening.as_of_date.desc(), CashOpening.service_center_id
                ).limit(30)
            )
        )
    return templates.TemplateResponse(
        request,
        "cash/entries.html",
        {
            "user": user,
            "centers": centers,
            "entries": entries,
            "openings": openings,
            "kinds": list(CashEntryKind),
            "subtypes": list(CollectionSubtype),
            "today": business_today().isoformat(),
            "locks": locks,
            "own_lock": locks.get(user.service_center_id) if user.role != UserRole.admin else None,
            "error": error,
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
    parsed_date = _parse_date(entry_date, business_today())
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

    closed = _is_closed(db, center_id, parsed_date)
    if user.role != UserRole.admin:
        if closed:
            return RedirectResponse("/cash/entries?error=cash.err_closed", status_code=303)
        if parsed_date > business_today():
            return RedirectResponse("/cash/entries?error=cash.err_future", status_code=303)

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

    entry = CashEntry(
        entry_date=parsed_date,
        service_center_id=center_id,
        kind=entry_kind,
        subtype=coll_subtype,
        amount=value,
        description=desc,
        created_by_id=user.id,
    )
    db.add(entry)
    if closed:
        db.flush()
        log_action(
            db,
            user,
            "create",
            "cash_entry",
            entry.id,
            "; ".join(f"{k}: {v}" for k, v in _entry_snapshot(entry).items()) + "; closed_period",
        )
    db.commit()
    return RedirectResponse("/cash/entries", status_code=303)


def _entry_snapshot(entry: CashEntry) -> dict:
    return {
        "date": entry.entry_date.isoformat(),
        "center": entry.service_center_id,
        "kind": entry.kind.value,
        "subtype": entry.subtype.value if entry.subtype else "",
        "amount": entry.amount,
        "description": entry.description,
    }


def _get_entry(db: Session, entry_id: int) -> CashEntry:
    entry = db.get(CashEntry, entry_id)
    if not entry:
        raise HTTPException(404)
    return entry


@router.get("/cash/entries/{entry_id}/edit", response_class=HTMLResponse)
def cash_entry_edit_page(
    entry_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    entry = _get_entry(db, entry_id)
    centers = list(db.scalars(select(ServiceCenter).order_by(ServiceCenter.id)))
    return templates.TemplateResponse(
        request,
        "cash/entry_edit.html",
        {
            "user": user,
            "entry": entry,
            "centers": centers,
            "kinds": list(CashEntryKind),
            "subtypes": list(CollectionSubtype),
            "closed": _is_closed(db, entry.service_center_id, entry.entry_date),
        },
    )


@router.post("/cash/entries/{entry_id}/edit")
def cash_entry_update(
    entry_id: int,
    kind: str = Form(...),
    entry_date: str = Form(...),
    amount: str = Form(...),
    description: str = Form(""),
    subtype: str = Form(""),
    service_center_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    entry = _get_entry(db, entry_id)
    try:
        entry_kind = CashEntryKind(kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bad_kind") from exc
    value = _parse_amount(amount)
    if value <= 0:
        raise HTTPException(status_code=400, detail="bad_amount")
    coll_subtype = None
    if entry_kind == CashEntryKind.collection:
        try:
            coll_subtype = CollectionSubtype(subtype)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="bad_subtype") from exc
    if not db.get(ServiceCenter, service_center_id):
        raise HTTPException(status_code=400, detail="no_center")

    new_date = _parse_date(entry_date, entry.entry_date)
    clash = existing_cash_entry(
        db,
        center_id=service_center_id,
        entry_date=new_date,
        kind=entry_kind,
        amount=value,
        description=(description or "").strip(),
    )
    if clash and clash.id != entry.id:
        raise HTTPException(status_code=400, detail="duplicate_entry")

    before = _entry_snapshot(entry)
    closed = _is_closed(db, entry.service_center_id, entry.entry_date) or _is_closed(
        db, service_center_id, new_date
    )
    entry.kind = entry_kind
    entry.subtype = coll_subtype
    entry.entry_date = new_date
    entry.amount = value
    entry.description = (description or "").strip()
    entry.service_center_id = service_center_id
    details = diff_text(before, _entry_snapshot(entry))
    if closed:
        details = f"{details}; closed_period"
    log_action(db, user, "edit", "cash_entry", entry.id, details)
    db.commit()
    return RedirectResponse("/cash/entries", status_code=303)


@router.post("/cash/entries/{entry_id}/delete")
def cash_entry_delete(
    entry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    entry = _get_entry(db, entry_id)
    snap = _entry_snapshot(entry)
    details = "; ".join(f"{k}: {v}" for k, v in snap.items())
    if _is_closed(db, entry.service_center_id, entry.entry_date):
        details = f"{details}; closed_period"
    db.delete(entry)
    log_action(db, user, "delete", "cash_entry", entry_id, details)
    db.commit()
    return RedirectResponse("/cash/entries", status_code=303)


@router.post("/cash/openings")
def cash_opening_set(
    as_of_date: str = Form(...),
    amount: str = Form(...),
    service_center_id: int = Form(...),
    is_start: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    if not db.get(ServiceCenter, service_center_id):
        raise HTTPException(status_code=400, detail="no_center")
    try:
        as_of = date.fromisoformat(as_of_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bad_date") from exc
    value = _parse_amount(amount)
    start = _checked(is_start)
    opening = db.scalar(
        select(CashOpening).where(
            CashOpening.service_center_id == service_center_id,
            CashOpening.as_of_date == as_of,
        )
    )
    before = _opening_snapshot(opening) if opening else None
    if opening:
        opening.amount = value
        opening.is_start = start
    else:
        opening = CashOpening(
            service_center_id=service_center_id, as_of_date=as_of, amount=value, is_start=start
        )
        db.add(opening)
    db.flush()
    after = _opening_snapshot(opening)
    log_action(
        db,
        user,
        "set",
        "cash_opening",
        opening.id,
        diff_text(before, after) if before else "; ".join(f"{k}: {v}" for k, v in after.items()),
    )
    db.commit()
    return RedirectResponse("/cash/entries", status_code=303)


def _checked(raw: str) -> bool:
    return raw in {"1", "on", "true"}


def _opening_snapshot(opening: CashOpening) -> dict:
    return {
        "center": opening.service_center_id,
        "date": opening.as_of_date.isoformat(),
        "amount": opening.amount,
        "start": opening.is_start,
    }


@router.get("/cash/openings/{opening_id}/edit", response_class=HTMLResponse)
def cash_opening_edit_page(
    opening_id: int,
    request: Request,
    error: str = Query(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    opening = db.get(CashOpening, opening_id)
    if not opening:
        raise HTTPException(404)
    centers = list(db.scalars(select(ServiceCenter).order_by(ServiceCenter.id)))
    return templates.TemplateResponse(
        request,
        "cash/opening_edit.html",
        {"user": user, "opening": opening, "centers": centers, "error": error},
    )


@router.post("/cash/openings/{opening_id}/edit")
def cash_opening_update(
    opening_id: int,
    as_of_date: str = Form(...),
    amount: str = Form(...),
    service_center_id: int = Form(...),
    is_start: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    opening = db.get(CashOpening, opening_id)
    if not opening:
        raise HTTPException(404)
    if not db.get(ServiceCenter, service_center_id):
        raise HTTPException(status_code=400, detail="no_center")
    try:
        as_of = date.fromisoformat(as_of_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bad_date") from exc
    clash = db.scalar(
        select(CashOpening).where(
            CashOpening.service_center_id == service_center_id,
            CashOpening.as_of_date == as_of,
            CashOpening.id != opening.id,
        )
    )
    if clash:
        return RedirectResponse(
            f"/cash/openings/{opening.id}/edit?error=admin.err_opening_taken", status_code=303
        )
    before = _opening_snapshot(opening)
    opening.service_center_id = service_center_id
    opening.as_of_date = as_of
    opening.amount = _parse_amount(amount)
    opening.is_start = _checked(is_start)
    details = diff_text(before, _opening_snapshot(opening))
    if details:
        log_action(db, user, "edit", "cash_opening", opening.id, details)
    db.commit()
    return RedirectResponse("/cash/entries", status_code=303)


@router.post("/cash/openings/{opening_id}/delete")
def cash_opening_delete(
    opening_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    opening = db.get(CashOpening, opening_id)
    if not opening:
        raise HTTPException(404)
    details = "; ".join(f"{k}: {v}" for k, v in _opening_snapshot(opening).items())
    db.delete(opening)
    log_action(db, user, "delete", "cash_opening", opening_id, details)
    db.commit()
    return RedirectResponse("/cash/entries", status_code=303)


@router.get("/more", response_class=HTMLResponse)
def more_page(request: Request, user: User = Depends(require_admin)):
    return templates.TemplateResponse(
        request,
        "more.html",
        {"user": user},
    )
