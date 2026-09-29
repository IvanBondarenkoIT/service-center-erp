#!/usr/bin/env python
"""Verify the app runs inside schema `scerp` the way pg-core is set up on the alt server.

Usage:
    PG_ADMIN_URL=postgresql://postgres:postgres@localhost:5432/granit python scripts/check_pg_schema.py [--reset]

The admin phase creates role/schemas like the server (search_path = scerp, core, no CREATE on public),
then the app phase runs in a subprocess as role `scerp`: create_all, ensure_schema twice, seed,
and checks that every table and enum type lives in `scerp`.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.config import normalize_database_url  # noqa: E402

ROLE = "scerp"
ROLE_PASSWORD = "scerp"
ENUM_TYPES = (
    "user_role",
    "order_status",
    "line_type",
    "payment_type",
    "cash_entry_kind",
    "collection_subtype",
)


def admin_phase(admin_url: str, reset: bool) -> str:
    engine = create_engine(normalize_database_url(admin_url), isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        if reset:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {ROLE} CASCADE"))
        conn.execute(
            text(
                "DO $$ BEGIN "
                f"IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{ROLE}') THEN "
                f"CREATE ROLE {ROLE} LOGIN PASSWORD '{ROLE_PASSWORD}'; "
                "END IF; END $$"
            )
        )
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {ROLE} AUTHORIZATION {ROLE}"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS core"))
        # A same-named table in core must not shadow or block the app's own table.
        conn.execute(text("CREATE TABLE IF NOT EXISTS core.users (id integer primary key)"))
        conn.execute(text(f"GRANT USAGE ON SCHEMA core TO {ROLE}"))
        conn.execute(text(f"GRANT SELECT ON ALL TABLES IN SCHEMA core TO {ROLE}"))
        conn.execute(text(f"ALTER ROLE {ROLE} SET search_path = {ROLE}, core"))
        conn.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
    engine.dispose()
    app_url = make_url(normalize_database_url(admin_url)).set(username=ROLE, password=ROLE_PASSWORD)
    return app_url.render_as_string(hide_password=False)


def app_phase() -> int:
    from app.database import Base, SessionLocal, engine
    import app.models  # noqa: F401
    from app.services.db_migrate import ensure_schema
    from app.services.seed import seed_defaults

    Base.metadata.create_all(bind=engine)
    ensure_schema()
    ensure_schema()
    db = SessionLocal()
    try:
        seed_defaults(db)
    finally:
        db.close()

    problems: list[str] = []
    expected = set(Base.metadata.tables)
    with engine.connect() as conn:
        current = conn.execute(text("SELECT current_schema()")).scalar()
        if current != ROLE:
            problems.append(f"current_schema() = {current!r}, expected {ROLE!r}")
        rows = conn.execute(
            text("SELECT schemaname, tablename FROM pg_tables WHERE tablename = ANY(:names)"),
            {"names": list(expected)},
        ).all()
        in_scerp = {t for s, t in rows if s == ROLE}
        missing = sorted(expected - in_scerp)
        if missing:
            problems.append(f"tables missing in {ROLE}: {missing}")
        in_public = sorted(t for s, t in rows if s == "public")
        if in_public:
            problems.append(f"tables created in public: {in_public}")
        types = conn.execute(
            text(
                "SELECT n.nspname, t.typname FROM pg_type t "
                "JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE t.typtype = 'e' AND t.typname = ANY(:names)"
            ),
            {"names": list(ENUM_TYPES)},
        ).all()
        enum_scerp = {t for s, t in types if s == ROLE}
        enum_missing = sorted(set(ENUM_TYPES) - enum_scerp)
        if enum_missing:
            problems.append(f"enum types missing in {ROLE}: {enum_missing}")
        enum_elsewhere = sorted(f"{s}.{t}" for s, t in types if s != ROLE)
        if enum_elsewhere:
            problems.append(f"enum types outside {ROLE}: {enum_elsewhere}")
        users = conn.execute(text("SELECT count(*) FROM users")).scalar()
        if not users:
            problems.append("seed did not create users in scerp.users")

    if problems:
        for p in problems:
            print(f"FAIL: {p}")
        return 1
    print(f"OK: {len(expected)} tables and {len(ENUM_TYPES)} enum types in schema {ROLE}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check app schema placement on Postgres")
    parser.add_argument("--reset", action="store_true", help="drop schema scerp first")
    parser.add_argument("--app-phase", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.app_phase:
        return app_phase()

    admin_url = (os.environ.get("PG_ADMIN_URL") or "").strip()
    if not admin_url:
        print("PG_ADMIN_URL is not set", file=sys.stderr)
        return 2
    app_url = admin_phase(admin_url, args.reset)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PG", "DATABASE_"))}
    env["DATABASE_URL"] = app_url
    env.setdefault("SECRET_KEY", "check-pg-schema-secret")
    env["APP_ENV"] = "development"
    return subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--app-phase"],
        cwd=str(ROOT),
        env=env,
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
