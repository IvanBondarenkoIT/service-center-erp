from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ErpGoodsCache, ErpSyncState
from app.proxy_client import ProxyClient

logger = logging.getLogger(__name__)

SyncMode = Literal["incremental", "full"]

_sync_lock = threading.Lock()

MACHINES_MAX_SQL = """
SELECT MAX(G.ID) AS MAX_ID
FROM GOODS G
JOIN GDSPARAMGDSREF R ON R.GOODSID = G.ID
WHERE R.PARAMID = 2 AND R.FIXVAL = 4
"""

MACHINES_BATCH_SQL = """
SELECT FIRST ? SKIP ?
  G.ID AS ERP_GOODS_ID, G.NAME AS NAME, G.OWNER AS GROUP_ID
FROM GOODS G
JOIN GDSPARAMGDSREF R ON R.GOODSID = G.ID
WHERE R.PARAMID = 2 AND R.FIXVAL = 4
ORDER BY G.ID
"""

MACHINES_NEW_SQL = """
SELECT FIRST ? SKIP ?
  G.ID AS ERP_GOODS_ID, G.NAME AS NAME, G.OWNER AS GROUP_ID
FROM GOODS G
JOIN GDSPARAMGDSREF R ON R.GOODSID = G.ID
WHERE R.PARAMID = 2 AND R.FIXVAL = 4
  AND G.ID > ?
ORDER BY G.ID
"""

PARTS_MAX_SQL = """
SELECT MAX(G.ID) AS MAX_ID
FROM GOODS G
WHERE G.OWNER IN (26287, 26894, 26889)
"""

PARTS_BATCH_SQL = """
SELECT FIRST ? SKIP ?
  G.ID AS ERP_GOODS_ID, G.NAME AS NAME, G.OWNER AS GROUP_ID
FROM GOODS G
WHERE G.OWNER IN (26287, 26894, 26889)
ORDER BY G.ID
"""

PARTS_NEW_SQL = """
SELECT FIRST ? SKIP ?
  G.ID AS ERP_GOODS_ID, G.NAME AS NAME, G.OWNER AS GROUP_ID
FROM GOODS G
WHERE G.OWNER IN (26287, 26894, 26889)
  AND G.ID > ?
ORDER BY G.ID
"""

REFRESH_BY_IDS_SQL = """
SELECT G.ID AS ERP_GOODS_ID, G.NAME AS NAME, G.OWNER AS GROUP_ID
FROM GOODS G
WHERE G.ID IN ({ids})
"""

SCOPE_CONFIG: dict[str, dict[str, Any]] = {
    "machines": {
        "kind": "machine",
        "max_sql": MACHINES_MAX_SQL,
        "batch_sql": MACHINES_BATCH_SQL,
        "new_sql": MACHINES_NEW_SQL,
    },
    "parts": {
        "kind": "part",
        "max_sql": PARTS_MAX_SQL,
        "batch_sql": PARTS_BATCH_SQL,
        "new_sql": PARTS_NEW_SQL,
    },
}


def get_proxy_client() -> ProxyClient:
    s = get_settings()
    return ProxyClient(
        base_url=s.proxy_api_url,
        token=s.proxy_api_token,
        timeout=s.proxy_api_timeout,
        max_retries=s.proxy_api_max_retries,
    )


def _content_hash(name: str, group_id: int | None, kind: str) -> str:
    payload = f"{name}|{group_id}|{kind}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _pause() -> None:
    time.sleep(get_settings().erp_sync_pause_ms / 1000.0)


def _get_or_create_state(db: Session, scope: str) -> ErpSyncState:
    state = db.scalar(select(ErpSyncState).where(ErpSyncState.scope == scope))
    if not state:
        state = ErpSyncState(scope=scope, last_max_goods_id=0, last_stats="{}")
        db.add(state)
        db.flush()
    return state


def _probe_max_id(client: ProxyClient, max_sql: str) -> int:
    rows = client.query(max_sql)
    if not rows:
        return 0
    val = rows[0].get("MAX_ID")
    return int(val) if val is not None else 0


def _upsert_rows(
    db: Session,
    rows: list[dict[str, Any]],
    kind: str,
    stats: dict[str, int],
    now: datetime,
) -> None:
    for row in rows:
        erp_id = int(row["ERP_GOODS_ID"])
        name = str(row.get("NAME") or "").strip()
        group_id_raw = row.get("GROUP_ID")
        group_id = int(group_id_raw) if group_id_raw is not None else None
        new_hash = _content_hash(name, group_id, kind)

        existing = db.scalar(select(ErpGoodsCache).where(ErpGoodsCache.erp_goods_id == erp_id))
        if existing:
            if existing.content_hash != new_hash or existing.name != name:
                existing.name = name
                existing.group_id = group_id
                existing.kind = kind
                existing.content_hash = new_hash
                existing.is_active = True
                existing.synced_at = now
                existing.last_seen_at = now
                stats["updated"] += 1
            else:
                existing.last_seen_at = now
                stats["unchanged"] += 1
        else:
            db.add(
                ErpGoodsCache(
                    erp_goods_id=erp_id,
                    name=name,
                    kind=kind,
                    group_id=group_id,
                    content_hash=new_hash,
                    is_active=True,
                    synced_at=now,
                    last_seen_at=now,
                )
            )
            stats["added"] += 1


def _fetch_batched(
    client: ProxyClient,
    sql: str,
    params_extra: list[Any] | None,
    stats: dict[str, int],
) -> list[dict[str, Any]]:
    settings = get_settings()
    batch_size = settings.erp_sync_batch_size
    max_batches = settings.erp_sync_max_batches
    all_rows: list[dict[str, Any]] = []
    skip = 0
    batches = 0

    while batches < max_batches:
        params: list[Any] = [batch_size, skip]
        if params_extra is not None:
            params.extend(params_extra)
        rows = client.query(sql, params)
        batches += 1
        stats["batches"] += 1
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < batch_size:
            break
        skip += batch_size
        _pause()

    if batches >= max_batches and len(all_rows) >= batch_size * max_batches:
        stats["has_more"] = 1

    return all_rows


def _refresh_stale(db: Session, client: ProxyClient, kind: str, stats: dict[str, int]) -> None:
    settings = get_settings()
    stale_cutoff = datetime.utcnow() - timedelta(hours=settings.erp_sync_stale_hours)
    stale_ids = list(
        db.scalars(
            select(ErpGoodsCache.erp_goods_id)
            .where(ErpGoodsCache.kind == kind, ErpGoodsCache.is_active.is_(True))
            .where(
                (ErpGoodsCache.synced_at < stale_cutoff)
                | (ErpGoodsCache.last_seen_at < stale_cutoff)
            )
            .order_by(ErpGoodsCache.synced_at.asc())
            .limit(settings.erp_sync_refresh_batch)
        )
    )
    if not stale_ids:
        return

    # Chunk IN lists to avoid huge queries
    chunk = 50
    now = datetime.utcnow()
    for i in range(0, len(stale_ids), chunk):
        ids_slice = stale_ids[i : i + chunk]
        id_list = ",".join(str(int(x)) for x in ids_slice)
        sql = REFRESH_BY_IDS_SQL.format(ids=id_list)
        rows = client.query(sql)
        _upsert_rows(db, rows, kind, stats, now)
        stats["refresh_batches"] = stats.get("refresh_batches", 0) + 1
        _pause()


def _sync_scope(
    db: Session,
    client: ProxyClient,
    scope: str,
    mode: SyncMode,
) -> dict[str, Any]:
    cfg = SCOPE_CONFIG[scope]
    kind = cfg["kind"]
    state = _get_or_create_state(db, scope)
    settings = get_settings()
    started = time.monotonic()
    stats: dict[str, Any] = {
        "scope": scope,
        "mode": mode,
        "added": 0,
        "updated": 0,
        "unchanged": 0,
        "batches": 0,
        "refresh_batches": 0,
        "skipped_probe": 0,
        "has_more": 0,
    }
    now = datetime.utcnow()

    max_id = _probe_max_id(client, cfg["max_sql"])
    stats["max_id"] = max_id

    skip_new = False
    if mode == "incremental" and state.last_sync_at and max_id <= state.last_max_goods_id:
        age = now - state.last_sync_at.replace(tzinfo=None)
        if age < timedelta(hours=settings.erp_sync_probe_skip_hours):
            skip_new = True
            stats["skipped_probe"] = 1

    if not skip_new:
        if mode == "full":
            rows = _fetch_batched(client, cfg["batch_sql"], None, stats)
        else:
            rows = _fetch_batched(client, cfg["new_sql"], [state.last_max_goods_id], stats)
        _upsert_rows(db, rows, kind, stats, now)

    if mode == "incremental":
        _refresh_stale(db, client, kind, stats)

    if max_id > state.last_max_goods_id:
        state.last_max_goods_id = max_id
    state.last_sync_at = now
    stats["duration_sec"] = round(time.monotonic() - started, 2)
    state.last_stats = json.dumps(stats, ensure_ascii=False)
    return stats


def sync_erp_catalog(db: Session, mode: SyncMode = "incremental") -> dict[str, Any]:
    client = get_proxy_client()
    if not client.configured:
        return {"skipped": 1, "reason": "proxy_not_configured"}

    if not _sync_lock.acquire(blocking=False):
        return {"skipped": 1, "reason": "sync_already_running"}

    try:
        for scope in SCOPE_CONFIG:
            st = _get_or_create_state(db, scope)
            if st.sync_in_progress:
                return {"skipped": 1, "reason": "sync_already_running"}
        for scope in SCOPE_CONFIG:
            _get_or_create_state(db, scope).sync_in_progress = True
        db.commit()

        results: dict[str, Any] = {"mode": mode, "scopes": {}}
        for scope in SCOPE_CONFIG:
            results["scopes"][scope] = _sync_scope(db, client, scope, mode)
            db.commit()

        totals = {"added": 0, "updated": 0, "unchanged": 0, "batches": 0, "has_more": False}
        for s in results["scopes"].values():
            totals["added"] += s.get("added", 0)
            totals["updated"] += s.get("updated", 0)
            totals["unchanged"] += s.get("unchanged", 0)
            totals["batches"] += s.get("batches", 0)
            if s.get("has_more"):
                totals["has_more"] = True
        results["totals"] = totals
        return results
    finally:
        for scope in SCOPE_CONFIG:
            st = db.scalar(select(ErpSyncState).where(ErpSyncState.scope == scope))
            if st:
                st.sync_in_progress = False
        db.commit()
        _sync_lock.release()


def get_sync_status(db: Session) -> list[dict[str, Any]]:
    states = list(db.scalars(select(ErpSyncState).order_by(ErpSyncState.scope)))
    out: list[dict[str, Any]] = []
    for st in states:
        try:
            stats = json.loads(st.last_stats) if st.last_stats else {}
        except json.JSONDecodeError:
            stats = {}
        out.append(
            {
                "scope": st.scope,
                "last_max_goods_id": st.last_max_goods_id,
                "last_sync_at": st.last_sync_at,
                "sync_in_progress": st.sync_in_progress,
                "stats": stats,
            }
        )
    return out


def count_cached_goods(db: Session, kind: str | None = None) -> int:
    stmt = select(func.count()).select_from(ErpGoodsCache).where(ErpGoodsCache.is_active.is_(True))
    if kind:
        stmt = stmt.where(ErpGoodsCache.kind == kind)
    return int(db.scalar(stmt) or 0)


def search_cached_goods(db: Session, q: str, kind: str | None = None, limit: int = 20):
    stmt = select(ErpGoodsCache).where(ErpGoodsCache.is_active.is_(True))
    if kind:
        stmt = stmt.where(ErpGoodsCache.kind == kind)
    if q:
        stmt = stmt.where(ErpGoodsCache.name.ilike(f"%{q.strip()}%"))
    stmt = stmt.order_by(ErpGoodsCache.name).limit(limit)
    return list(db.scalars(stmt))
