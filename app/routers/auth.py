from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import create_session_token, verify_password
from app.config import get_settings
from app.database import get_db
from app.deps import home_path, try_current_user
from app.i18n import LOCALE_COOKIE, make_translator, normalize_locale, resolve_locale
from app.models import User
from app.templating import templates

router = APIRouter(tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user: User | None = Depends(try_current_user)):
    if user:
        return RedirectResponse(home_path(user), status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": None},
    )


@router.post("/login")
def login_submit(
    request: Request,
    response: Response,
    login: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.login == login.strip()))
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        locale = resolve_locale(request)
        t = make_translator(locale)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": t("auth.bad_credentials")},
            status_code=401,
        )
    settings = get_settings()
    token = create_session_token(user.id)
    redirect = RedirectResponse(home_path(user), status_code=303)
    redirect.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        samesite="lax",
        max_age=settings.session_max_age,
    )
    redirect.set_cookie(
        LOCALE_COOKIE,
        user.locale or "ru",
        samesite="lax",
        max_age=settings.session_max_age,
    )
    return redirect


@router.post("/logout")
@router.get("/logout")
def logout():
    settings = get_settings()
    redirect = RedirectResponse("/login", status_code=303)
    redirect.delete_cookie(settings.session_cookie_name)
    return redirect


@router.post("/locale")
def set_locale(
    request: Request,
    locale: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
    user: User | None = Depends(try_current_user),
):
    loc = normalize_locale(locale)
    if user:
        user.locale = loc
        db.commit()
    dest = next if next.startswith("/") and not next.startswith("//") else "/"
    redirect = RedirectResponse(dest, status_code=303)
    settings = get_settings()
    redirect.set_cookie(
        LOCALE_COOKIE,
        loc,
        samesite="lax",
        max_age=settings.session_max_age,
    )
    return redirect
