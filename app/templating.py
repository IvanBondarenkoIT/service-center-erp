from __future__ import annotations

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


templates = Jinja2Templates(
    directory=str(BASE_DIR / "templates"),
    context_processors=[_i18n_context],
)
