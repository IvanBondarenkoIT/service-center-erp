#!/usr/bin/env python
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal  # noqa: E402
from app.services.seed import seed_defaults  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        seed_defaults(db)
        print("Seed OK")
    finally:
        db.close()


if __name__ == "__main__":
    main()
