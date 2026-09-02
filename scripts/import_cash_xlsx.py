#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.database import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.services.import_cash_xlsx import import_cash_xlsx  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import cash book xlsx (expense, collection, opening) into a service center"
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=str(ROOT / "data" / "input" / "Cash register service 2026.xlsx"),
        help="path to cash register workbook",
    )
    parser.add_argument("--center", default="batumi", help="service center code")
    parser.add_argument("--user", default=None, help="login stored as created_by")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    db = SessionLocal()
    try:
        created_by_id = None
        if args.user:
            user = db.scalar(select(User).where(User.login == args.user))
            if user is None:
                raise SystemExit(f"Unknown user: {args.user}")
            created_by_id = user.id
        stats = import_cash_xlsx(
            db, path, center_code=args.center, created_by_id=created_by_id
        )
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
