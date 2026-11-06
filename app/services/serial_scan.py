from __future__ import annotations

import uuid
from urllib.parse import parse_qs, unquote, urlparse

# Fake SN values mechanics type when there is no machine (parts-only sale).
_BLANK_SERIAL_TOKENS = frozenset(
    {
        "no",
        "n/a",
        "na",
        "none",
        "нет",
        "нету",
        "без",
        "-",
        "—",
        "–",
        ".",
        "_",
    }
)


def serial_from_scan(raw: str | None) -> str:
    """Extract a machine serial from scanner text (plain SN or URL with sn/serial)."""
    text = unquote(str(raw or "")).strip()
    if not text:
        return ""
    lowered = text.lower()
    if "://" in text or text.startswith("www.") or ("?" in text and "=" in text):
        if "://" not in text and text.startswith("www."):
            text = "https://" + text
        parsed = urlparse(text if "://" in text else "https://dummy.local/" + text.lstrip("/"))
        qs = parse_qs(parsed.query)
        for key in ("sn", "serial", "serial_number", "s"):
            values = qs.get(key) or []
            if values and str(values[0]).strip():
                return str(values[0]).strip()
        path = (parsed.path or "").rstrip("/")
        if path:
            segment = path.rsplit("/", 1)[-1].strip()
            if segment and segment.lower() not in {"", "index.html", "scan"}:
                return unquote(segment)
        return text.strip()
    if lowered.startswith("sn:") or lowered.startswith("sn="):
        return text.split(":", 1)[-1].split("=", 1)[-1].strip()
    return text


def is_blank_serial(raw: str | None) -> bool:
    serial = serial_from_scan(raw)
    if not serial:
        return True
    return serial.casefold() in _BLANK_SERIAL_TOKENS


def normalize_machine_serial(raw: str | None) -> str:
    """Return a real SN, or empty when missing/fake (NO, нет, -)."""
    if is_blank_serial(raw):
        return ""
    return serial_from_scan(raw)


def make_placeholder_serial(prefix: str = "NEED-SERIAL-") -> str:
    """Unique internal SN so blank machines never share history."""
    base = (prefix or "NEED-SERIAL-").strip() or "NEED-SERIAL-"
    return f"{base}{uuid.uuid4().hex[:12].upper()}"
