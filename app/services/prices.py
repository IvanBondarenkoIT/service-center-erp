from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppSetting, PromoOffer

DIAGNOSTIC_PRICE_KEY = "diagnostic_price"


def get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.get(AppSetting, key)
    return row.value if row else default


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


def _money(raw: str | Decimal | None) -> Decimal:
    try:
        return Decimal(str(raw or 0).replace(",", ".").strip() or "0")
    except InvalidOperation:
        return Decimal("0")


def diagnostic_price(db: Session) -> Decimal:
    return _money(get_setting(db, DIAGNOSTIC_PRICE_KEY, "0"))


def set_diagnostic_price(db: Session, value: str | Decimal) -> Decimal:
    amount = _money(value)
    set_setting(db, DIAGNOSTIC_PRICE_KEY, f"{amount:.2f}")
    return amount


def active_promos(db: Session, extra: list[PromoOffer] | None = None) -> list[PromoOffer]:
    rows = list(
        db.scalars(select(PromoOffer).where(PromoOffer.is_active.is_(True)).order_by(PromoOffer.name))
    )
    seen = {p.id for p in rows}
    for offer in extra or []:
        if offer and offer.id not in seen:
            rows.insert(0, offer)
            seen.add(offer.id)
    return rows
