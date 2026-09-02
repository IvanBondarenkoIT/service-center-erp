#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.services.db_migrate import ensure_erp_schema  # noqa: E402
from app.services.erp_sync import sync_erp_catalog  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync ERP goods catalog into local cache")
    parser.add_argument(
        "--mode",
        choices=("incremental", "full"),
        default="incremental",
        help="incremental: new IDs + stale refresh; full: batched full scan",
    )
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    ensure_erp_schema()

    db = SessionLocal()
    try:
        result = sync_erp_catalog(db, mode=args.mode)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        db.close()


if __name__ == "__main__":
    main()
