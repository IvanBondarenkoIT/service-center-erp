from __future__ import annotations

import pytest

from app.services.phones import normalize_phone


@pytest.mark.parametrize(
    "raw",
    ["+995 599 40 23 00", "995599402300", "00995599402300", "599-40-23-00", "599402300"],
)
def test_georgian_variants_match(raw: str) -> None:
    assert normalize_phone(raw) == "599402300"


def test_foreign_number_kept() -> None:
    assert normalize_phone("+380 71 348 04 11") == "380713480411"


def test_empty() -> None:
    assert normalize_phone("") == ""
    assert normalize_phone(None) == ""
