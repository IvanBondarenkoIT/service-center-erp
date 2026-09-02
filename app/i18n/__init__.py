from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from fastapi import Request

SUPPORTED_LOCALES = ("ru", "en", "ka")
DEFAULT_LOCALE = "ru"
LOCALE_COOKIE = "scerp_locale"

_CATALOG_DIR = Path(__file__).resolve().parent


@lru_cache
def _load_catalog(locale: str) -> dict[str, Any]:
    path = _CATALOG_DIR / f"{locale}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_locale(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if raw in SUPPORTED_LOCALES:
        return raw
    return DEFAULT_LOCALE


def resolve_locale(request: Request, user_locale: str | None = None) -> str:
    cookie = request.cookies.get(LOCALE_COOKIE)
    if cookie:
        return normalize_locale(cookie)
    if user_locale:
        return normalize_locale(user_locale)
    return DEFAULT_LOCALE


def _lookup(catalog: dict[str, Any], key: str) -> str | None:
    node: Any = catalog
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, str) else None


def translate(key: str, locale: str = DEFAULT_LOCALE, **kwargs: Any) -> str:
    locale = normalize_locale(locale)
    text = _lookup(_load_catalog(locale), key)
    if text is None and locale != DEFAULT_LOCALE:
        text = _lookup(_load_catalog(DEFAULT_LOCALE), key)
    if text is None:
        text = key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            pass
    return text


def make_translator(locale: str) -> Callable[..., str]:
    loc = normalize_locale(locale)

    def t(key: str, **kwargs: Any) -> str:
        return translate(key, loc, **kwargs)

    return t


def catalog_key_set(locale: str) -> set[str]:
    def walk(node: Any, prefix: str) -> set[str]:
        keys: set[str] = set()
        if not isinstance(node, dict):
            return keys
        for k, v in node.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                keys |= walk(v, path)
            else:
                keys.add(path)
        return keys

    return walk(_load_catalog(normalize_locale(locale)), "")
