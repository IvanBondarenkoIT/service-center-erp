#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal  # noqa: E402
from app.services.import_excel import import_excel  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Coffee Machines Excel into SC ERP")
    parser.add_argument(
        "path",
        nargs="?",
        default=str(
            ROOT.parents[1]
            / "data"
            / "input"
            / "Сервис центр ЕРП"
            / "Coffee Machines Table 2025.xlsx"
        ),
    )
    parser.add_argument("--center", default="tbilisi", help="service center code")
    parser.add_argument("--assignee", default=None, help="user login for assignee")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    db = SessionLocal()
    try:
        stats = import_excel(
            db, path, default_center_code=args.center, assignee_login=args.assignee
        )
        print("Import OK:", stats)
    finally:
        db.close()


if __name__ == "__main__":
    main()
