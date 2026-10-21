from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from decimal import Decimal, InvalidOperation

from app.auth import hash_password
from app.database import get_db
from app.deps import require_admin_screen
from app.models import OrderLine, PromoOffer, ServiceCenter, User, UserRole
from app.services.audit import ENTITIES, diff_text, log_action, recent_audit
from app.services.prices import diagnostic_price, set_diagnostic_price
from app.templating import templates

router = APIRouter(prefix="/admin", tags=["admin"])

MIN_PASSWORD = 6


def _money(raw: str) -> Decimal:
    try:
        return Decimal(str(raw).replace(",", ".").strip() or "0")
    except InvalidOperation:
        return Decimal("0")


def _centers(db: Session) -> list[ServiceCenter]:
    return list(db.scalars(select(ServiceCenter).order_by(ServiceCenter.id)))


def _parse_role(raw: str) -> UserRole:
    try:
        return UserRole(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bad_role") from exc


def _parse_center(db: Session, raw: str) -> int | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    if not raw.isdigit() or not db.get(ServiceCenter, int(raw)):
        raise HTTPException(status_code=400, detail="no_center")
    return int(raw)


def _snapshot(u: User) -> dict:
    return {
        "login": u.login,
        "name": u.full_name,
        "role": u.role.value,
        "center": u.service_center_id,
        "active": u.is_active,
    }


def _users_page(request: Request, db: Session, user: User, error: str = ""):
    users = list(
        db.scalars(
            select(User)
            .options(joinedload(User.service_center))
            .order_by(User.is_active.desc(), User.role, User.login)
        )
    )
    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {
            "user": user,
            "users": users,
            "centers": _centers(db),
            "roles": list(UserRole),
            "error": error,
        },
        status_code=400 if error else 200,
    )


@router.get("/users", response_class=HTMLResponse)
def users_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    return _users_page(request, db, user)


@router.post("/users")
def users_create(
    request: Request,
    login: str = Form(...),
    full_name: str = Form(""),
    role: str = Form(...),
    service_center_id: str = Form(""),
    password: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    login = login.strip()
    if not login:
        return _users_page(request, db, user, "admin.err_login")
    if db.scalar(select(User).where(User.login == login)):
        return _users_page(request, db, user, "admin.err_login_taken")
    if len(password) < MIN_PASSWORD:
        return _users_page(request, db, user, "admin.err_password")
    new_user = User(
        login=login,
        full_name=full_name.strip(),
        role=_parse_role(role),
        service_center_id=_parse_center(db, service_center_id),
        password_hash=hash_password(password),
        is_active=True,
    )
    db.add(new_user)
    db.flush()
    log_action(
        db,
        user,
        "create",
        "user",
        new_user.id,
        "; ".join(f"{k}: {v}" for k, v in _snapshot(new_user).items()),
    )
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/users/{user_id}", response_class=HTMLResponse)
def user_edit_page(
    user_id: int,
    request: Request,
    error: str = Query(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404)
    return templates.TemplateResponse(
        request,
        "admin/user_edit.html",
        {
            "user": user,
            "target": target,
            "centers": _centers(db),
            "roles": list(UserRole),
            "error": error,
        },
    )


@router.post("/users/{user_id}")
def user_update(
    user_id: int,
    full_name: str = Form(""),
    role: str = Form(...),
    service_center_id: str = Form(""),
    is_active: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404)
    new_role = _parse_role(role)
    active = is_active in {"1", "on", "true"}
    if target.id == user.id and (new_role != UserRole.admin or not active):
        return RedirectResponse(f"/admin/users/{user_id}?error=admin.err_self", status_code=303)
    if password and len(password) < MIN_PASSWORD:
        return RedirectResponse(f"/admin/users/{user_id}?error=admin.err_password", status_code=303)

    before = _snapshot(target)
    target.full_name = full_name.strip()
    target.role = new_role
    target.service_center_id = _parse_center(db, service_center_id)
    target.is_active = active
    details = diff_text(before, _snapshot(target))
    if password:
        target.password_hash = hash_password(password)
        details = f"{details}; password changed" if details else "password changed"
    if details:
        log_action(db, user, "edit", "user", target.id, details)
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/audit", response_class=HTMLResponse)
def audit_page(
    request: Request,
    entity: str = Query(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    if entity not in ENTITIES:
        entity = ""
    return templates.TemplateResponse(
        request,
        "admin/audit.html",
        {
            "user": user,
            "entries": recent_audit(db, entity=entity),
            "entities": ENTITIES,
            "entity": entity,
        },
    )


def _promo_counts(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(OrderLine.promo_id, func.count(OrderLine.id))
        .where(OrderLine.promo_id.is_not(None))
        .group_by(OrderLine.promo_id)
    )
    return {row[0]: row[1] for row in rows}


@router.get("/prices", response_class=HTMLResponse)
def prices_page(
    request: Request,
    error: str = Query(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    promos = list(db.scalars(select(PromoOffer).order_by(PromoOffer.is_active.desc(), PromoOffer.name)))
    return templates.TemplateResponse(
        request,
        "admin/prices.html",
        {
            "user": user,
            "diagnostic_price": diagnostic_price(db),
            "promos": promos,
            "promo_counts": _promo_counts(db),
            "error": error,
        },
    )


@router.post("/prices/diagnostic")
def diagnostic_price_save(
    amount: str = Form("0"),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    value = set_diagnostic_price(db, amount)
    log_action(db, user, "set", "promo", None, f"diagnostic_price → {value}")
    db.commit()
    return RedirectResponse("/admin/prices", status_code=303)


@router.post("/prices/promos")
def promo_create(
    name: str = Form(...),
    client_amount: str = Form("0"),
    val_amount: str = Form("0"),
    is_active: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    name = name.strip()
    if not name:
        return RedirectResponse("/admin/prices?error=admin.err_promo_name", status_code=303)
    offer = PromoOffer(
        name=name,
        client_amount=_money(client_amount),
        val_amount=_money(val_amount),
        is_active=is_active in {"1", "on", "true"},
    )
    db.add(offer)
    db.flush()
    log_action(
        db,
        user,
        "create",
        "promo",
        offer.id,
        f"{offer.name}; client {offer.client_amount}; val {offer.val_amount}",
    )
    db.commit()
    return RedirectResponse("/admin/prices", status_code=303)


@router.post("/prices/promos/{promo_id}")
def promo_update(
    promo_id: int,
    name: str = Form(...),
    client_amount: str = Form("0"),
    val_amount: str = Form("0"),
    is_active: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_screen),
):
    offer = db.get(PromoOffer, promo_id)
    if not offer:
        raise HTTPException(404)
    name = name.strip()
    if not name:
        return RedirectResponse("/admin/prices?error=admin.err_promo_name", status_code=303)
    before = {
        "name": offer.name,
        "client": offer.client_amount,
        "val": offer.val_amount,
        "active": offer.is_active,
    }
    offer.name = name
    offer.client_amount = _money(client_amount)
    offer.val_amount = _money(val_amount)
    offer.is_active = is_active in {"1", "on", "true"}
    details = diff_text(
        before,
        {
            "name": offer.name,
            "client": offer.client_amount,
            "val": offer.val_amount,
            "active": offer.is_active,
        },
    )
    if details:
        log_action(db, user, "edit", "promo", offer.id, details)
    db.commit()
    return RedirectResponse("/admin/prices", status_code=303)
