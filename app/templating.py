from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.i18n import SUPPORTED_LOCALES, make_translator, resolve_locale

BASE_DIR = Path(__file__).resolve().parent.parent


def _i18n_context(request: Request) -> dict:
    locale = resolve_locale(request)
    return {
        "locale": locale,
        "t": make_translator(locale),
        "supported_locales": SUPPORTED_LOCALES,
    }


def _asset_version() -> str:
    digest = hashlib.sha256()
    for path in sorted((BASE_DIR / "static").glob("*.*")):
        if path.suffix in {".js", ".css"}:
            digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


templates = Jinja2Templates(
    directory=str(BASE_DIR / "templates"),
    context_processors=[_i18n_context],
)
templates.env.globals["asset_v"] = _asset_version()
