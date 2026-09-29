from __future__ import annotations

import re


def normalize_phone(raw: str | None) -> str:
    """Digits only; Georgian numbers (+995 / 995 / 00995 + 9 digits) reduced to 9 local digits."""
    if not raw:
        return ""
    digits = re.sub(r"\D+", "", str(raw))
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("995") and len(digits) == 12:
        digits = digits[3:]
    return digits


def format_phone_display(phone: str) -> str:
    p = normalize_phone(phone)
    if len(p) == 9:
        return f"{p[0:3]}-{p[3:5]}-{p[5:7]}-{p[7:9]}"
    return phone or ""
