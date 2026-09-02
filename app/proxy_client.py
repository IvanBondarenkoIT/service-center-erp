from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)


class ProxyClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 90.0,
        max_retries: int = 3,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._max_retries = max(1, int(max_retries))

    @property
    def configured(self) -> bool:
        return bool(self._base and self._token)

    def query(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        if not self.configured:
            raise RuntimeError("Proxy API is not configured")
        url = f"{self._base}/api/query"
        payload = {"query": sql, "params": params or []}
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=self._timeout)
                if resp.status_code == 429:
                    time.sleep(5)
                    continue
                if 500 <= resp.status_code < 600:
                    time.sleep(min(2**attempt, 30))
                    continue
                resp.raise_for_status()
                return normalize_proxy_rows(resp.json())
            except (requests.RequestException, ValueError) as e:
                last_exc = e
                if attempt + 1 >= self._max_retries:
                    break
                time.sleep(min(2**attempt, 10))
        assert last_exc is not None
        raise last_exc


def normalize_proxy_rows(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, list):
        if not body:
            return []
        if isinstance(body[0], dict):
            return body
        raise ValueError("Proxy returned a list of non-objects")
    if not isinstance(body, dict):
        raise ValueError(f"Unexpected proxy body type: {type(body)}")
    if "rows" in body and isinstance(body["rows"], list):
        rows = body["rows"]
        if not rows:
            return []
        if isinstance(rows[0], dict):
            return rows
        cols = body.get("columns") or body.get("fields") or []
        if cols and isinstance(rows[0], (list, tuple)):
            return [dict(zip(cols, row)) for row in rows]
    if "data" in body and isinstance(body["data"], list):
        return body["data"]
    raise ValueError("Unsupported proxy response shape")
