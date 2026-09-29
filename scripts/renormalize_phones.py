#!/usr/bin/env python
"""Re-apply normalize_phone to clients.phone; conflicting duplicates are only reported."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import Client  # noqa: E402
from app.services.phones import normalize_phone  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize stored client phones")
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        clients = list(db.scalars(select(Client)))
        taken = {c.phone: c for c in clients}
        changed = conflicts = 0
        for c in clients:
            if c.phone.startswith("noname-"):
                continue
            new = normalize_phone(c.phone)
            if not new or new == c.phone:
                continue
            other = taken.get(new)
            if other and other.id != c.id:
                conflicts += 1
                print(f"conflict: client #{c.id} {c.phone!r} -> {new!r} already used by #{other.id}")
                continue
            print(f"client #{c.id}: {c.phone!r} -> {new!r}")
            taken.pop(c.phone, None)
            taken[new] = c
            c.phone = new
            changed += 1
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(f"changed={changed} conflicts={conflicts} applied={args.apply}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
