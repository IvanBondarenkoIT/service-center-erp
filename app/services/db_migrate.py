from __future__ import annotations

from sqlalchemy import inspect, text

from app.database import engine


def _try_alter(conn, stmt: str) -> None:
    try:
        conn.execute(text(stmt))
    except Exception:
        pass


def _column_names(insp, table: str) -> set[str]:
    if table not in set(insp.get_table_names()):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def ensure_schema() -> None:
    """Create new tables and add columns/enum values create_all will not alter."""
    from app.models import CashEntry, CashOpening, ErpGoodsCache, ErpSyncState  # noqa: F401

    insp = inspect(engine)
    existing = set(insp.get_table_names())
    dialect = engine.dialect.name

    if "erp_sync_state" not in existing:
        ErpSyncState.__table__.create(bind=engine, checkfirst=True)
    if "erp_goods_cache" not in existing:
        ErpGoodsCache.__table__.create(bind=engine, checkfirst=True)
    if "cash_entries" not in existing:
        CashEntry.__table__.create(bind=engine, checkfirst=True)
    if "cash_openings" not in existing:
        CashOpening.__table__.create(bind=engine, checkfirst=True)

    insp = inspect(engine)
    tables = set(insp.get_table_names())
    erp_cols = _column_names(insp, "erp_goods_cache")
    user_cols = _column_names(insp, "users")
    order_cols = _column_names(insp, "service_orders")

    with engine.begin() as conn:
        if "erp_goods_cache" in tables:
            if "content_hash" not in erp_cols:
                _try_alter(
                    conn,
                    "ALTER TABLE erp_goods_cache ADD COLUMN content_hash VARCHAR(64) DEFAULT ''",
                )
            if "is_active" not in erp_cols:
                if dialect == "sqlite":
                    _try_alter(
                        conn,
                        "ALTER TABLE erp_goods_cache ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1",
                    )
                else:
                    _try_alter(
                        conn,
                        "ALTER TABLE erp_goods_cache ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE",
                    )
            if "last_seen_at" not in erp_cols:
                _try_alter(conn, "ALTER TABLE erp_goods_cache ADD COLUMN last_seen_at TIMESTAMP")

        if "users" in tables and "locale" not in user_cols:
            _try_alter(
                conn,
                "ALTER TABLE users ADD COLUMN locale VARCHAR(8) NOT NULL DEFAULT 'ru'",
            )

        if dialect == "postgresql":
            _try_alter(conn, "ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'accountant'")
            _try_alter(
                conn,
                "DO $$ BEGIN "
                "CREATE TYPE order_status AS ENUM "
                "('in_progress', 'waiting_part', 'ready', 'issued'); "
                "EXCEPTION WHEN duplicate_object THEN NULL; END $$",
            )
            _try_alter(conn, "ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'issued'")
            if "service_orders" in tables and "status" not in order_cols:
                _try_alter(
                    conn,
                    "ALTER TABLE service_orders ADD COLUMN status order_status "
                    "NOT NULL DEFAULT 'in_progress'",
                )
        elif "service_orders" in tables and "status" not in order_cols:
            _try_alter(
                conn,
                "ALTER TABLE service_orders ADD COLUMN status VARCHAR(32) "
                "NOT NULL DEFAULT 'in_progress'",
            )

        if "service_orders" in tables and "paid_at" not in order_cols:
            _try_alter(conn, "ALTER TABLE service_orders ADD COLUMN paid_at TIMESTAMP")

        if "cash_entries" in tables:
            conn.execute(
                text(
                    "DELETE FROM cash_entries WHERE id NOT IN ("
                    "SELECT id FROM ("
                    "SELECT MIN(id) AS id FROM cash_entries "
                    "GROUP BY service_center_id, entry_date, kind, amount, description"
                    "))"
                )
            )
            _try_alter(
                conn,
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_cash_entry_dedupe "
                "ON cash_entries (service_center_id, entry_date, kind, amount, description)",
            )


def ensure_erp_schema() -> None:
    """Back-compat alias."""
    ensure_schema()
