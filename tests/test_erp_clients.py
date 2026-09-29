from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Client, ErpClientCache, ErpSyncState, ServiceOrder
from app.services.erp_clients import find_erp_client, parse_orgn_row, sync_erp_clients
from tests.helpers import login, settings


def _local_phone() -> str:
    return f"5{uuid.uuid4().int % 100_000_000:08d}"


class FakeProxy:
    def __init__(self, orgn_rows, purchase_rows):
        self.orgn_rows = orgn_rows
        self.purchase_rows = purchase_rows

    def query(self, sql, params=None):
        if "FROM KASSDATA" in sql:
            return self.purchase_rows
        if "O.ID > ?" in sql:
            after = params[-1]
            return [r for r in self.orgn_rows if r["ID"] > after][: params[0]]
        return []


def test_parse_orgn_row_card_number_not_a_name() -> None:
    p = parse_orgn_row(
        {"ID": 1, "NAME": "2200011012131", "FULLNAME": " Rusudan K ", "PHONE": "995599402300"}
    )
    assert p["name"] == "Rusudan K"
    assert p["card_no"] == "2200011012131"
    assert p["phone_norm"] == "599402300"

    p2 = parse_orgn_row({"ID": 2, "NAME": "2200011022819", "FULLNAME": "", "PHONE": "", "PHONENBR": "598201670"})
    assert p2["name"] == ""
    assert p2["phone_norm"] == "598201670"


def test_sync_clients_and_purchases() -> None:
    base = 5_000_000 + uuid.uuid4().int % 1_000_000
    phone = _local_phone()
    proxy = FakeProxy(
        [
            {"ID": base + 1, "NAME": "2200000000001", "FULLNAME": "Nino Test", "PHONE": "995" + phone},
            {"ID": base + 2, "NAME": "2200000000002", "FULLNAME": "", "PHONE": phone},
        ],
        [
            {"ORGNID": base + 1, "CNT": 3, "TOTAL": 120.5, "LAST_DAT": "2026-09-20T00:00:00"},
            {"ORGNID": base + 2, "CNT": 1, "TOTAL": 10, "LAST_DAT": "2026-09-25T00:00:00"},
        ],
    )
    db = SessionLocal()
    try:
        state = db.scalar(select(ErpSyncState).where(ErpSyncState.scope == "clients"))
        if state:
            state.last_max_goods_id = base
            state.last_sync_at = None
            db.commit()
        stats = sync_erp_clients(db, proxy, "incremental")
        db.commit()
        assert stats["added"] == 2

        match = find_erp_client(db, "+995 " + phone)
        assert match is not None
        assert match.name == "Nino Test"
        assert match.purchase_count == 4
        assert match.purchase_sum == Decimal("130.50")
        assert match.last_purchase_at == date(2026, 9, 25)
    finally:
        db.close()


def _add_erp_client(phone: str, name: str, purchases: int) -> None:
    db = SessionLocal()
    try:
        db.add(
            ErpClientCache(
                erp_orgn_id=7_000_000 + uuid.uuid4().int % 1_000_000,
                name=name,
                phone_raw="995" + phone,
                phone_norm=phone,
                purchase_count=purchases,
                purchase_sum=Decimal("55.00"),
                last_purchase_at=date(2026, 8, 1) if purchases else None,
            )
        )
        db.commit()
    finally:
        db.close()


def test_history_shows_erp_purchases_and_name(client) -> None:
    phone = _local_phone()
    _add_erp_client(phone, "Shop Buyer", 2)
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    r = client.get("/orders/partials/history-by-client", params={"phone": "+995" + phone})
    assert r.status_code == 200
    assert "Shop Buyer" in r.text
    assert 'data-erp-name="Shop Buyer"' in r.text
    assert "Клиент у нас делал покупки" in r.text
    assert "01.08.2026" in r.text


def test_history_erp_known_without_purchases(client) -> None:
    phone = _local_phone()
    _add_erp_client(phone, "No Buys", 0)
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    r = client.get("/orders/partials/history-by-client", params={"phone": phone})
    assert "Клиент есть в базе магазина" in r.text


def test_intake_fills_name_from_erp_and_saves_model(client) -> None:
    phone = _local_phone()
    _add_erp_client(phone, "Erp Name", 1)
    serial = f"SN-ERP-{uuid.uuid4().hex[:8].upper()}"
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    r = client.post(
        "/orders/intake",
        data={
            "new_machine_serial": serial,
            "new_client_phone": "00995" + phone,
            "new_client_name": "",
            "new_machine_model": "Delonghi ECAM 22.110.B",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    oid = int(r.headers["location"].rstrip("/").rsplit("/", 1)[-1])
    db = SessionLocal()
    try:
        order = db.get(ServiceOrder, oid)
        assert order is not None
        assert order.machine.model_name == "Delonghi ECAM 22.110.B"
        c = db.scalar(select(Client).where(Client.phone == phone))
        assert c is not None
        assert c.name == "Erp Name"
    finally:
        db.close()
