from __future__ import annotations

import uuid

from sqlalchemy import delete

from app.database import SessionLocal
from app.models import ErpGoodsCache
from app.services.erp_sync import normalize_model, search_cached_goods
from tests.helpers import login, settings

_BASE_ID = 900_000 + uuid.uuid4().int % 50_000
_NAMES = [
    "Delonghi ECAM 22.110.B",
    "Delonghi ECAM22.110.SB",
    "Delonghi ECAM 22.360",
    "DELONGHI ESAM 4500",
]


def _seed() -> None:
    db = SessionLocal()
    try:
        db.execute(
            delete(ErpGoodsCache).where(
                ErpGoodsCache.erp_goods_id.between(_BASE_ID, _BASE_ID + len(_NAMES))
            )
        )
        for i, name in enumerate(_NAMES):
            db.add(ErpGoodsCache(erp_goods_id=_BASE_ID + i, name=name, kind="machine", is_active=True))
        db.commit()
    finally:
        db.close()


def _names(q: str) -> list[str]:
    db = SessionLocal()
    try:
        return [i.name for i in search_cached_goods(db, q, kind="machine", limit=50) if i.name in _NAMES]
    finally:
        db.close()


def test_normalize_model() -> None:
    assert normalize_model("Delonghi ECAM 22.110.B") == "delonghiecam22110b"
    assert normalize_model("ECAM22-110 sb") == "ecam22110sb"


def test_search_ignores_dots_spaces_and_case() -> None:
    _seed()
    variants = {"Delonghi ECAM 22.110.B", "Delonghi ECAM22.110.SB"}
    assert set(_names("ecam22110")) == variants
    assert set(_names("ECAM 22.110")) == variants
    assert set(_names("ecam 22 110")) == variants
    assert _names("22110sb") == ["Delonghi ECAM22.110.SB"]
    assert _names("delonghi 4500") == ["DELONGHI ESAM 4500"]


def test_exact_model_ranked_first() -> None:
    _seed()
    assert _names("ecam22110b")[0] == "Delonghi ECAM 22.110.B"
    assert _names("ecam22360") == ["Delonghi ECAM 22.360"]


def test_erp_suggest_endpoint_normalized(client) -> None:
    _seed()
    login(client, "mechanic_batumi", settings.seed_mechanic_password)
    r = client.get("/dict/erp-suggest", params={"q": "ecam22110", "kind": "machine"})
    assert r.status_code == 200
    assert "ECAM 22.110.B" in r.text
    assert "ECAM 22.360" not in r.text
