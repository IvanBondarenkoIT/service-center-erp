from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ErpClientCache, ErpSyncState
from app.proxy_client import ProxyClient
from app.services.phones import normalize_phone

SyncMode = Literal["incremental", "full"]

SCOPE = "clients"

CLIENTS_AFTER_ID_SQL = """
SELECT FIRST ?
  O.ID AS ID, O.NAME AS NAME, O.FULLNAME AS FULLNAME, O.PHONE AS PHONE, O.PHONENBR AS PHONENBR
FROM ORGN O
WHERE O.ID > ?
ORDER BY O.ID
"""

CLIENTS_EDITED_SQL = """
SELECT FIRST ?
  O.ID AS ID, O.NAME AS NAME, O.FULLNAME AS FULLNAME, O.PHONE AS PHONE, O.PHONENBR AS PHONENBR
FROM ORGN O
WHERE O.LASTEDIT >= CAST(? AS TIMESTAMP) AND O.ID <= ?
ORDER BY O.ID
"""

PURCHASES_SQL = """
SELECT K.ORGNID AS ORGNID, COUNT(*) AS CNT, SUM(K.SUMMA) AS TOTAL, MAX(K.DAT_) AS LAST_DAT
FROM KASSDATA K
WHERE K.ORGNID IS NOT NULL AND COALESCE(K.DELETED, 0) = 0
GROUP BY K.ORGNID
"""


def _clean(value: Any) -> str:
    return str(value or "").strip()


def parse_orgn_row(row: dict[str, Any]) -> dict[str, Any]:
    """Map a Granit ORGN row to cache fields; NAME often holds a loyalty card number."""
    raw_name = _clean(row.get("NAME"))
    full_name = _clean(row.get("FULLNAME"))
    card_no = raw_name if raw_name.isdigit() else ""
    name = full_name or ("" if card_no else raw_name)
    phone_raw = _clean(row.get("PHONE")) or _clean(row.get("PHONENBR"))
    return {
        "erp_orgn_id": int(row["ID"]),
        "name": name[:255],
        "card_no": card_no[:64],
        "phone_raw": phone_raw[:64],
        "phone_norm": normalize_phone(phone_raw)[:32],
    }


def _hash(fields: dict[str, Any]) -> str:
    payload = "|".join(str(fields[k]) for k in ("name", "card_no", "phone_raw"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:19]).date()
    except ValueError:
        return None


def _upsert_clients(db: Session, rows: list[dict[str, Any]], stats: dict[str, Any], now: datetime) -> None:
    if not rows:
        return
    parsed = [parse_orgn_row(r) for r in rows]
    ids = [p["erp_orgn_id"] for p in parsed]
    existing = {
        c.erp_orgn_id: c
        for c in db.scalars(select(ErpClientCache).where(ErpClientCache.erp_orgn_id.in_(ids)))
    }
    for p in parsed:
        h = _hash(p)
        cur = existing.get(p["erp_orgn_id"])
        if cur:
            if cur.content_hash != h:
                cur.name = p["name"]
                cur.card_no = p["card_no"]
                cur.phone_raw = p["phone_raw"]
                cur.phone_norm = p["phone_norm"]
                cur.content_hash = h
                cur.synced_at = now
                stats["updated"] += 1
            else:
                stats["unchanged"] += 1
        else:
            db.add(ErpClientCache(**p, content_hash=h, is_active=True, synced_at=now))
            stats["added"] += 1
    db.flush()


def _fetch_keyset(
    client: ProxyClient,
    sql: str,
    extra: list[Any],
    start_id: int,
    stats: dict[str, Any],
    on_batch,
) -> int:
    settings = get_settings()
    batch = settings.erp_clients_batch_size
    last_id = start_id
    for _ in range(settings.erp_clients_max_batches):
        params: list[Any] = [batch]
        params.extend(extra)
        if sql is CLIENTS_AFTER_ID_SQL:
            params.append(last_id)
        rows = client.query(sql, params)
        stats["batches"] += 1
        if not rows:
            return last_id
        on_batch(rows)
        last_id = max(int(r["ID"]) for r in rows)
        if len(rows) < batch or sql is not CLIENTS_AFTER_ID_SQL:
            return last_id
        time.sleep(settings.erp_sync_pause_ms / 1000.0)
    stats["has_more"] = 1
    return last_id


def _apply_purchases(db: Session, client: ProxyClient, stats: dict[str, Any]) -> None:
    rows = client.query(PURCHASES_SQL)
    by_id = {int(r["ORGNID"]): r for r in rows if r.get("ORGNID") is not None}
    touched = 0
    for c in db.scalars(select(ErpClientCache).where(ErpClientCache.erp_orgn_id.in_(list(by_id)))):
        r = by_id[c.erp_orgn_id]
        cnt = int(r.get("CNT") or 0)
        total = Decimal(str(r.get("TOTAL") or 0)).quantize(Decimal("0.01"))
        last = _parse_date(r.get("LAST_DAT"))
        if c.purchase_count != cnt or c.purchase_sum != total or c.last_purchase_at != last:
            c.purchase_count = cnt
            c.purchase_sum = total
            c.last_purchase_at = last
            touched += 1
    stats["purchases_updated"] = touched
    stats["purchase_clients"] = len(by_id)


def sync_erp_clients(db: Session, client: ProxyClient, mode: SyncMode = "incremental") -> dict[str, Any]:
    state = db.scalar(select(ErpSyncState).where(ErpSyncState.scope == SCOPE))
    if not state:
        state = ErpSyncState(scope=SCOPE, last_max_goods_id=0, last_stats="{}")
        db.add(state)
        db.flush()

    started = time.monotonic()
    now = datetime.utcnow()
    stats: dict[str, Any] = {
        "scope": SCOPE,
        "mode": mode,
        "added": 0,
        "updated": 0,
        "unchanged": 0,
        "batches": 0,
        "has_more": 0,
    }

    def on_batch(rows: list[dict[str, Any]]) -> None:
        _upsert_clients(db, rows, stats, now)

    start_id = 0 if mode == "full" else state.last_max_goods_id
    max_id = _fetch_keyset(client, CLIENTS_AFTER_ID_SQL, [], start_id, stats, on_batch)

    if mode == "incremental" and state.last_sync_at and start_id:
        since = state.last_sync_at.replace(tzinfo=None) - timedelta(days=1)
        _fetch_keyset(
            client,
            CLIENTS_EDITED_SQL,
            [since.strftime("%Y-%m-%d %H:%M:%S"), start_id],
            start_id,
            stats,
            on_batch,
        )

    _apply_purchases(db, client, stats)

    if max_id > state.last_max_goods_id:
        state.last_max_goods_id = max_id
    state.last_sync_at = now
    stats["duration_sec"] = round(time.monotonic() - started, 2)
    state.last_stats = json.dumps(stats, ensure_ascii=False)
    return stats


def count_cached_clients(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(ErpClientCache).where(ErpClientCache.is_active.is_(True))
        )
        or 0
    )


@dataclass
class ErpClientMatch:
    name: str
    card_no: str
    purchase_count: int
    purchase_sum: Decimal
    last_purchase_at: date | None


def find_erp_client(db: Session, phone: str) -> ErpClientMatch | None:
    """Granit may hold several ORGN rows per phone (one per loyalty card); merge them."""
    phone_n = normalize_phone(phone)
    if len(phone_n) < 7:
        return None
    rows = list(
        db.scalars(
            select(ErpClientCache)
            .where(ErpClientCache.phone_norm == phone_n, ErpClientCache.is_active.is_(True))
            .order_by(ErpClientCache.erp_orgn_id.desc())
        )
    )
    if not rows:
        return None
    named = next((r for r in rows if r.name), rows[0])
    dates = [r.last_purchase_at for r in rows if r.last_purchase_at]
    return ErpClientMatch(
        name=named.name,
        card_no=next((r.card_no for r in rows if r.card_no), ""),
        purchase_count=sum(r.purchase_count or 0 for r in rows),
        purchase_sum=sum((r.purchase_sum or Decimal("0") for r in rows), Decimal("0")),
        last_purchase_at=max(dates) if dates else None,
    )
