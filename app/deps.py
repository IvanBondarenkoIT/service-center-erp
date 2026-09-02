from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import load_session_token
from app.config import get_settings
from app.database import get_db
from app.models import User, UserRole


class NotAuthenticated(Exception):
    pass


class AccountantOnlyCash(Exception):
    """Accountant must stay on the cash screens."""


def home_path(user: User) -> str:
    if user.role == UserRole.accountant:
        return "/cash"
    return "/"


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise NotAuthenticated()
    user_id = load_session_token(token)
    if not user_id:
        raise NotAuthenticated()
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise NotAuthenticated()
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


def require_admin_screen(user: User = Depends(get_current_user)) -> User:
    """Admin UI pages: accountant goes to cash, mechanic gets 403."""
    if user.role == UserRole.accountant:
        raise AccountantOnlyCash()
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


def get_staff_user(user: User = Depends(get_current_user)) -> User:
    if user.role == UserRole.accountant:
        raise AccountantOnlyCash()
    return user


def require_cash_editor(user: User = Depends(get_current_user)) -> User:
    if user.role == UserRole.accountant:
        raise HTTPException(status_code=403, detail="Accountant is read-only")
    return user


def try_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    try:
        return get_current_user(request, db)
    except NotAuthenticated:
        return None
