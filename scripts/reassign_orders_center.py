#!/usr/bin/env python
"""Move imported orders from one service center to another (and its mechanic)."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.database import SessionLocal
from app.models import ServiceCenter, ServiceOrder, User, UserRole


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-center", required=True)
    parser.add_argument("--to-center", required=True)
    parser.add_argument("--since", required=True, help="YYYY-MM-DD")
    parser.add_argument("--until", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()
    date_from = date.fromisoformat(args.since)
    date_to = date.fromisoformat(args.until)

    db = SessionLocal()
    try:
        src = db.scalar(select(ServiceCenter).where(ServiceCenter.code == args.from_center))
        dst = db.scalar(select(ServiceCenter).where(ServiceCenter.code == args.to_center))
        if src is None or dst is None:
            raise SystemExit(f"center not found: {args.from_center!r} -> {args.to_center!r}")
        mechanic = db.scalar(
            select(User).where(
                User.role == UserRole.mechanic,
                User.service_center_id == dst.id,
            )
        )
        if mechanic is None:
            raise SystemExit(f"no mechanic for {args.to_center}")
        orders = list(
            db.scalars(
                select(ServiceOrder).where(
                    ServiceOrder.service_center_id == src.id,
                    ServiceOrder.order_date >= date_from,
                    ServiceOrder.order_date <= date_to,
                )
            )
        )
        for order in orders:
            order.service_center_id = dst.id
            order.assignee_id = mechanic.id
        db.commit()
        print(
            {
                "moved": len(orders),
                "from": src.code,
                "to": dst.code,
                "assignee": mechanic.login,
            }
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
