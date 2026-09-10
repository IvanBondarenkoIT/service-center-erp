from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import Settings, get_settings
from app.models import IssueReason, ServiceCenter, User, UserRole

DEFAULT_CENTERS = [
    ("batumi", "Сервис Батуми", "Батуми"),
    ("tbilisi", "Сервис Тбилиси 1", "Тбилиси"),
    ("tbilisi2", "Сервис Тбилиси 2", "Тбилиси"),
]

DEFAULT_REASONS = [
    "декальцинация",
    "диагностика",
    "не греет",
    "нет воды",
    "чистка капучинатора",
    "замена запчасти",
    "гарантийный ремонт",
    "регулировка",
]

_OLD_TBILISI_LOGIN = "mechanic_tbilisi"
_NEW_TBILISI_LOGIN = "mechanic_tbilisi1"


@dataclass(frozen=True)
class SeedUserSpec:
    login: str
    role: UserRole
    center_code: str | None
    full_name: str


def parse_seed_users(raw: str) -> list[SeedUserSpec]:
    specs: list[SeedUserSpec] = []
    for chunk in (raw or "").split("|"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split(":", 3)]
        while len(parts) < 4:
            parts.append("")
        login, role_raw, center, name = parts
        if not login:
            continue
        specs.append(
            SeedUserSpec(
                login=login,
                role=UserRole(role_raw),
                center_code=center or None,
                full_name=name or login,
            )
        )
    return specs


def seed_password_env_key(login: str) -> str:
    return "SEED_PASSWORD_" + login.upper().replace("-", "_")


def resolve_seed_password(login: str, role: UserRole, settings: Settings) -> str:
    per_user = (os.environ.get(seed_password_env_key(login)) or "").strip()
    if per_user:
        return per_user
    if role is UserRole.admin:
        return settings.seed_admin_password
    if role is UserRole.accountant:
        return settings.seed_accountant_password
    return settings.seed_mechanic_password


def _ensure_center(
    db: Session,
    centers: dict[str, ServiceCenter],
    code: str,
    name: str = "",
    city: str = "",
) -> ServiceCenter:
    if code in centers:
        return centers[code]
    center = db.scalar(select(ServiceCenter).where(ServiceCenter.code == code))
    if not center:
        center = ServiceCenter(code=code, name=name or code, city=city)
        db.add(center)
        db.flush()
    elif name and center.name != name:
        center.name = name
        if city:
            center.city = city
    centers[code] = center
    return center


def _rename_legacy_tbilisi_login(db: Session) -> None:
    old = db.scalar(select(User).where(User.login == _OLD_TBILISI_LOGIN))
    new = db.scalar(select(User).where(User.login == _NEW_TBILISI_LOGIN))
    if old and not new:
        old.login = _NEW_TBILISI_LOGIN
        if old.full_name in {"Механик Тбилиси", _OLD_TBILISI_LOGIN}:
            old.full_name = "Механик Тбилиси 1"
        db.flush()


def seed_defaults(db: Session) -> None:
    settings = get_settings()
    centers: dict[str, ServiceCenter] = {}
    for code, name, city in DEFAULT_CENTERS:
        _ensure_center(db, centers, code, name=name, city=city)

    _rename_legacy_tbilisi_login(db)

    for spec in parse_seed_users(settings.seed_users):
        if spec.center_code:
            _ensure_center(db, centers, spec.center_code)
        existing = db.scalar(select(User).where(User.login == spec.login))
        if existing:
            continue
        db.add(
            User(
                login=spec.login,
                full_name=spec.full_name,
                role=spec.role,
                service_center_id=centers[spec.center_code].id if spec.center_code else None,
                password_hash=hash_password(
                    resolve_seed_password(spec.login, spec.role, settings)
                ),
            )
        )

    for reason_name in DEFAULT_REASONS:
        exists = db.scalar(select(IssueReason).where(IssueReason.name == reason_name))
        if not exists:
            db.add(IssueReason(name=reason_name))

    db.commit()
