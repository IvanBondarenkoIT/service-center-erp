from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import AuditLog, User

ENTITIES = (
    "order",
    "cash_entry",
    "cash_opening",
    "user",
    "client",
    "machine",
    "reason",
    "promo",
)


def log_action(
    db: Session,
    user: User | None,
    action: str,
    entity: str,
    entity_id: int | None = None,
    details: str = "",
) -> None:
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            entity=entity,
            entity_id=entity_id,
            details=details[:4000],
        )
    )


def diff_text(before: dict[str, Any], after: dict[str, Any]) -> str:
    parts = []
    for key, old in before.items():
        new = after.get(key)
        if str(old) != str(new):
            parts.append(f"{key}: {old} → {new}")
    return "; ".join(parts)


def recent_audit(db: Session, entity: str = "", limit: int = 200) -> list[AuditLog]:
    stmt = (
        select(AuditLog)
        .options(joinedload(AuditLog.user))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
    )
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    return list(db.scalars(stmt))
