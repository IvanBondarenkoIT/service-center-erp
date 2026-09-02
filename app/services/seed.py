from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import get_settings
from app.models import IssueReason, ServiceCenter, User, UserRole


DEFAULT_CENTERS = [
    ("batumi", "Сервис Батуми", "Батуми"),
    ("tbilisi", "Сервис Тбилиси", "Тбилиси"),
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


def seed_defaults(db: Session) -> None:
    settings = get_settings()
    centers: dict[str, ServiceCenter] = {}
    for code, name, city in DEFAULT_CENTERS:
        center = db.scalar(select(ServiceCenter).where(ServiceCenter.code == code))
        if not center:
            center = ServiceCenter(code=code, name=name, city=city)
            db.add(center)
            db.flush()
        centers[code] = center

    users_spec = [
        ("admin", "Администратор", UserRole.admin, None, settings.seed_admin_password),
        (
            "mechanic_batumi",
            "Механик Батуми",
            UserRole.mechanic,
            "batumi",
            settings.seed_mechanic_password,
        ),
        (
            "mechanic_tbilisi",
            "Механик Тбилиси",
            UserRole.mechanic,
            "tbilisi",
            settings.seed_mechanic_password,
        ),
        (
            "mechanic_tbilisi2",
            "Механик Тбилиси 2",
            UserRole.mechanic,
            "tbilisi2",
            settings.seed_mechanic_password,
        ),
        (
            "accountant",
            "Бухгалтер",
            UserRole.accountant,
            None,
            settings.seed_accountant_password,
        ),
    ]
    for login, full_name, role, center_code, password in users_spec:
        existing = db.scalar(select(User).where(User.login == login))
        if existing:
            continue
        db.add(
            User(
                login=login,
                full_name=full_name,
                role=role,
                service_center_id=centers[center_code].id if center_code else None,
                password_hash=hash_password(password),
            )
        )

    for reason_name in DEFAULT_REASONS:
        exists = db.scalar(select(IssueReason).where(IssueReason.name == reason_name))
        if not exists:
            db.add(IssueReason(name=reason_name))

    db.commit()
