from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse


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
