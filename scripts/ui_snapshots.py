#!/usr/bin/env python3
"""UI screenshots + mobile metrics for mobile-first stages.

Requires: pip install -r requirements-dev.txt && playwright install chromium
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from html import escape
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "ui"

PASSWORDS = {
    "admin": "admin123",
    "mechanic_batumi": "mechanic123",
    "accountant": "accountant123",
}

VIEWPORTS = {
    "mobile": {"width": 390, "height": 844, "is_mobile": True, "has_touch": True, "device_scale_factor": 2},
    "desktop": {"width": 1366, "height": 900, "is_mobile": False, "has_touch": False, "device_scale_factor": 1},
}


def _require_playwright():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        print(
            "Playwright is not installed.\n"
            "  pip install -r requirements-dev.txt\n"
            "  playwright install chromium",
            file=sys.stderr,
        )
        raise SystemExit(2)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_http(url: str, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    last: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if 200 <= resp.status < 500:
                    return
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(0.4)
    raise RuntimeError(f"Server did not become ready at {url}: {last}")


def _git_branch() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        name = out.strip().replace("/", "-")
        return name or "local"
    except Exception:  # noqa: BLE001
        return "local"


def _slug(path: str, role: str, size: str) -> str:
    safe = path.strip("/") or "home"
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", safe)
    return f"{role}__{size}__{safe}"


class HttpClient:
    """Minimal cookie-aware HTTP client (stdlib)."""

    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.cookies: dict[str, str] = {}

    def _headers(self) -> dict[str, str]:
        if not self.cookies:
            return {}
        return {"Cookie": "; ".join(f"{k}={v}" for k, v in self.cookies.items())}

    def _store(self, resp: Any) -> None:
        # http.client headers may be multi
        raw = resp.headers.get_all("Set-Cookie") if hasattr(resp.headers, "get_all") else None
        if not raw:
            one = resp.headers.get("Set-Cookie")
            raw = [one] if one else []
        for item in raw:
            if not item:
                continue
            part = item.split(";", 1)[0]
            if "=" in part:
                k, v = part.split("=", 1)
                self.cookies[k.strip()] = v.strip()

    def request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | list[tuple[str, str]] | None = None,
        allow_redirects: bool = False,
    ) -> tuple[int, str, str]:
        url = path if path.startswith("http") else f"{self.base}{path}"
        body = None
        headers = self._headers()
        if data is not None:
            from urllib.parse import urlencode

            body = urlencode(data, doseq=True).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler)
        if not allow_redirects:

            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *args, **kwargs):  # noqa: ANN002, ANN003
                    return None

            opener = urllib.request.build_opener(NoRedirect)

        try:
            resp = opener.open(req, timeout=30)
        except urllib.error.HTTPError as exc:
            self._store(exc)
            loc = exc.headers.get("Location") or ""
            text = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return exc.code, loc, text
        with resp:
            self._store(resp)
            loc = resp.headers.get("Location") or ""
            text = resp.read().decode("utf-8", errors="replace")
            return resp.status, loc, text

    def login(self, login: str, password: str) -> None:
        self.cookies.clear()
        code, loc, _ = self.request(
            "POST",
            "/login",
            data={"login": login, "password": password},
        )
        if code not in (303, 302, 200):
            raise RuntimeError(f"login failed for {login}: HTTP {code}")
        if code == 200 and "/login" in loc:
            raise RuntimeError(f"login rejected for {login}")

    def post(self, path: str, data: dict[str, Any] | list[tuple[str, str]]) -> tuple[int, str]:
        code, loc, _ = self.request("POST", path, data=data)
        return code, loc


def _db_maps(db_path: Path) -> tuple[dict[str, int], dict[str, int]]:
    conn = sqlite3.connect(db_path)
    try:
        centers = {row[0]: row[1] for row in conn.execute("SELECT code, id FROM service_centers")}
        users = {row[0]: row[1] for row in conn.execute("SELECT login, id FROM users")}
        return centers, users
    finally:
        conn.close()


def _order_id(location: str) -> int:
    return int(location.rstrip("/").rsplit("/", 1)[-1])


def _seed_demo(base: str, db_path: Path) -> dict[str, Any]:
    """Deterministic demo data via the same POST forms as tests."""
    centers, users = _db_maps(db_path)
    today = date.today().isoformat()
    http = HttpClient(base)
    http.login("admin", PASSWORDS["admin"])

    def save(payload: dict[str, Any] | list[tuple[str, str]]) -> int:
        code, loc = http.post("/orders/save", payload)
        if code not in (303, 302) or "/orders/" not in loc:
            raise RuntimeError(f"order save failed: {code} {loc}")
        return _order_id(loc)

    def base_order(
        *,
        serial: str,
        phone: str,
        center: str,
        assignee: str,
        status: str = "in_progress",
        model: str = "Jura E8",
        name: str = "UI Snapshot",
        amount: str = "35.50",
        payment: str = "Cash",
        line_type: str = "work",
        description: str = "cleaning",
        is_warranty: str = "0",
        warranty_eur: str = "0",
    ) -> dict[str, str]:
        return {
            "order_date": today,
            "assignee_id": str(users[assignee]),
            "service_center_id": str(centers[center]),
            "new_machine_serial": serial,
            "new_machine_model": model,
            "new_client_phone": phone,
            "new_client_name": name,
            "line_type": line_type,
            "description": description,
            "part_code": "",
            "payment_type": payment,
            "is_warranty": is_warranty,
            "amount": amount,
            "warranty_eur": warranty_eur,
            "status": status,
            "comment": "",
        }

    ids: dict[str, int] = {}

    # ~10 orders across centers / statuses
    specs = [
        ("in_progress", "batumi", "mechanic_batumi", "SN-UI-001", "5990000001"),
        ("waiting_part", "batumi", "mechanic_batumi", "SN-UI-002", "5990000002"),
        ("ready", "batumi", "mechanic_batumi", "SN-UI-003", "5990000003"),
        ("in_progress", "tbilisi", "mechanic_tbilisi1", "SN-UI-004", "5990000004"),
        ("waiting_part", "tbilisi", "mechanic_tbilisi1", "SN-UI-005", "5990000005"),
        ("ready", "tbilisi2", "mechanic_tbilisi2", "SN-UI-006", "5990000006"),
        ("in_progress", "tbilisi2", "mechanic_tbilisi2", "SN-UI-007", "5990000007"),
    ]
    for status, center, assignee, serial, phone in specs:
        key = f"{status}_{serial}"
        ids[key] = save(
            base_order(
                serial=serial,
                phone=phone,
                center=center,
                assignee=assignee,
                status=status,
            )
        )

    # Multi-line: work/Cash, part/Card, warranty EUR
    multi = [
        ("order_date", today),
        ("assignee_id", str(users["mechanic_batumi"])),
        ("service_center_id", str(centers["batumi"])),
        ("new_machine_serial", "SN-UI-MULTI"),
        ("new_machine_model", "Jura S8"),
        ("new_client_phone", "5990000010"),
        ("new_client_name", "Multi Line"),
        ("status", "in_progress"),
        ("comment", "multi-line demo"),
        ("line_type", "work"),
        ("description", "cleaning"),
        ("part_code", ""),
        ("payment_type", "Cash"),
        ("is_warranty", "0"),
        ("amount", "40.00"),
        ("warranty_eur", "0"),
        ("line_type", "part"),
        ("description", "seal"),
        ("part_code", "SEAL-1"),
        ("payment_type", "Card"),
        ("is_warranty", "0"),
        ("amount", "12.50"),
        ("warranty_eur", "0"),
        ("line_type", "work"),
        ("description", "warranty visit"),
        ("part_code", ""),
        ("payment_type", "garanty"),
        ("is_warranty", "1"),
        ("amount", "0"),
        ("warranty_eur", "5.00"),
    ]
    ids["multi"] = save(multi)
    # Stage 4 needs the multi-line order as the primary "in progress" screenshot.
    ids["in_progress_open"] = ids["multi"]

    # Blank SN (parts-only)
    ids["blank_sn"] = save(
        base_order(
            serial="",
            phone="5990000011",
            center="batumi",
            assignee="mechanic_batumi",
            model="",
            name="Parts Only",
            amount="18.00",
            line_type="part",
            description="filter",
            payment="Cash",
        )
    )

    # Paid / issued (3–4)
    paid_specs = [
        ("SN-UI-P01", "5990000021", "Cash", "50.00"),
        ("SN-UI-P02", "5990000022", "Card", "33.00"),
        ("SN-UI-P03", "5990000023", "Transfer", "27.00"),
        ("SN-UI-P04", "5990000024", "Cash", "15.00"),
    ]
    issued_ids: list[int] = []
    for serial, phone, pay, amount in paid_specs:
        oid = save(
            base_order(
                serial=serial,
                phone=phone,
                center="batumi",
                assignee="mechanic_batumi",
                amount=amount,
                payment=pay,
            )
        )
        code, loc = http.post(f"/orders/{oid}/pay", {})
        if code not in (303, 302):
            raise RuntimeError(f"pay failed for {oid}: {code} {loc}")
        issued_ids.append(oid)
    ids["issued"] = issued_ids[0]
    ids["issued_ids"] = issued_ids  # type: ignore[assignment]

    # Cash: expense + collection + opening
    code, _ = http.post(
        "/cash/entries",
        {
            "kind": "expense",
            "entry_date": today,
            "amount": "12.00",
            "description": "UI snapshot expense",
            "subtype": "",
            "service_center_id": str(centers["batumi"]),
        },
    )
    if code not in (303, 302):
        raise RuntimeError(f"cash expense failed: {code}")

    code, _ = http.post(
        "/cash/entries",
        {
            "kind": "collection",
            "entry_date": today,
            "amount": "100.00",
            "description": "UI snapshot collection",
            "subtype": "bank",
            "service_center_id": str(centers["batumi"]),
        },
    )
    if code not in (303, 302):
        raise RuntimeError(f"cash collection failed: {code}")

    code, _ = http.post(
        "/cash/openings",
        {
            "as_of_date": today,
            "amount": "200.00",
            "service_center_id": str(centers["batumi"]),
            "is_start": "1",
        },
    )
    if code not in (303, 302):
        raise RuntimeError(f"cash opening failed: {code}")

    conn = sqlite3.connect(db_path)
    try:
        entry_id = conn.execute(
            "SELECT id FROM cash_entries WHERE description LIKE 'UI snapshot expense%' LIMIT 1"
        ).fetchone()
        opening_id = conn.execute(
            "SELECT id FROM cash_openings ORDER BY id DESC LIMIT 1"
        ).fetchone()
        admin_id = users["admin"]
    finally:
        conn.close()

    ids["cash_entry"] = int(entry_id[0]) if entry_id else 0
    ids["cash_opening"] = int(opening_id[0]) if opening_id else 0
    ids["admin_user"] = admin_id
    return ids


def _pages_for(role: str, ids: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (label, path) pages available to the role."""
    in_prog = f"/orders/{ids['in_progress_open']}"
    issued = f"/orders/{ids['issued']}"
    common_cash = [
        ("cash", "/cash"),
        ("cash_entries", "/cash/entries"),
    ]
    if role == "admin":
        pages = [
            ("home", "/"),
            ("intake", "/orders/intake"),
            ("orders_new", "/orders/new"),
            ("order_in_progress", in_prog),
            ("order_issued", issued),
            *common_cash,
            ("cash_entry_edit", f"/cash/entries/{ids['cash_entry']}/edit"),
            ("cash_opening_edit", f"/cash/openings/{ids['cash_opening']}/edit"),
            ("reports", "/reports"),
            ("more", "/more"),
            ("dict_clients", "/dict/clients"),
            ("dict_machines", "/dict/machines"),
            ("dict_reasons", "/dict/reasons"),
            ("dict_erp", "/dict/erp-catalog"),
            ("admin_users", "/admin/users"),
            ("admin_user_edit", f"/admin/users/{ids['admin_user']}"),
            ("admin_audit", "/admin/audit"),
            ("admin_order_history", "/admin/order-history"),
            ("admin_prices", "/admin/prices"),
        ]
    elif role == "mechanic_batumi":
        pages = [
            ("home", "/"),
            ("intake", "/orders/intake"),
            ("orders_new", "/orders/new"),
            ("order_in_progress", in_prog),
            ("order_issued", issued),
            *common_cash,
            ("cash_entry_edit", f"/cash/entries/{ids['cash_entry']}/edit"),
        ]
    else:  # accountant
        pages = [
            ("home", "/"),  # redirects to cash typically
            *common_cash,
            ("reports", "/reports"),
            ("admin_order_history", "/admin/order-history"),
        ]
    return pages


METRIC_JS = """
(expectedWidth) => {
  // Prefer the configured viewport width: with is_mobile, window.innerWidth can grow
  // with the document and hide horizontal overflow.
  const layoutWidth = Number(expectedWidth) || window.innerWidth;
  const scrollWidth = Math.max(
    document.documentElement.scrollWidth,
    document.body ? document.body.scrollWidth : 0
  );

  function isVisible(el) {
    if (!el || el.getClientRects().length === 0) return false;
    let node = el;
    while (node && node.nodeType === 1) {
      const st = getComputedStyle(node);
      if (st.display === 'none' || st.visibility === 'hidden') return false;
      node = node.parentElement;
    }
    return true;
  }

  function elLabel(el) {
    const tag = el.tagName.toLowerCase();
    const cls = (el.className && typeof el.className === 'string')
      ? '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.')
      : '';
    return tag + cls;
  }

  const interactive = Array.from(document.querySelectorAll(
    'a, button, input, select, textarea, label:has(input[type=checkbox]), label:has(input[type=radio])'
  ));
  const smallTap = [];
  for (const el of interactive) {
    if (!isVisible(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.height > 0 && r.height < 44) {
      smallTap.push({
        tag: el.tagName.toLowerCase(),
        id: el.id || '',
        name: el.getAttribute('name') || '',
        h: Math.round(r.height * 10) / 10,
        w: Math.round(r.width * 10) / 10,
      });
    }
  }

  const fields = Array.from(document.querySelectorAll('input, select, textarea'));
  const skipTypes = new Set([
    'hidden', 'checkbox', 'radio', 'button', 'submit', 'reset', 'file', 'image', 'range', 'color',
  ]);
  let smallFont = 0;
  for (const el of fields) {
    if (skipTypes.has(el.type || '')) continue;
    if (!isVisible(el)) continue;
    const fs = parseFloat(getComputedStyle(el).fontSize || '0');
    if (fs > 0 && fs < 16) smallFont += 1;
  }

  const clipped = [];
  const all = Array.from(document.querySelectorAll('body *'));
  for (const el of all) {
    if (!isVisible(el)) continue;
    if (el.closest && el.closest('.hscroll')) continue;
    let ancestorHit = false;
    for (const prev of clipped) {
      if (prev._el && prev._el.contains(el)) { ancestorHit = true; break; }
    }
    if (ancestorHit) continue;
    const st = getComputedStyle(el);
    const ox = st.overflowX;
    const r = el.getBoundingClientRect();
    let reason = '';
    let contentW = 0;
    let boxW = 0;
    if (
      (ox === 'hidden' || ox === 'clip' || ox === 'auto' || ox === 'scroll')
      && el.scrollWidth > el.clientWidth + 1
    ) {
      reason = 'overflow-x:' + ox;
      contentW = el.scrollWidth;
      boxW = el.clientWidth;
    } else if (
      st.position !== 'fixed'
      && r.width > 0
      && r.right > layoutWidth + 1
    ) {
      reason = 'past-viewport';
      contentW = Math.round(r.right);
      boxW = layoutWidth;
    } else {
      continue;
    }
    clipped.push({
      _el: el,
      el: elLabel(el),
      reason,
      content: contentW,
      box: boxW,
    });
  }

  return {
    viewportWidth: layoutWidth,
    innerWidth: window.innerWidth,
    scrollWidth,
    horizontalOverflow: scrollWidth > layoutWidth + 1,
    smallTapCount: smallTap.length,
    smallTapSample: smallTap.slice(0, 25),
    smallFontFields: smallFont,
    clippedCount: clipped.length,
    clipped: clipped.slice(0, 15).map(({ el, reason, content, box }) => ({
      el, reason, content, box,
    })),
  };
}
"""


def _capture(
    *,
    base: str,
    out_dir: Path,
    ids: dict[str, Any],
    locale: str | None,
) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    report: dict[str, Any] = {
        "name": out_dir.name,
        "base_url": base,
        "locale": locale or "ru",
        "pages": [],
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    shots = out_dir / "shots"
    shots.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for role, password in PASSWORDS.items():
            for size_name, vp in VIEWPORTS.items():
                context = browser.new_context(
                    viewport={"width": vp["width"], "height": vp["height"]},
                    is_mobile=vp["is_mobile"],
                    has_touch=vp["has_touch"],
                    device_scale_factor=vp["device_scale_factor"],
                    locale="ka-GE" if locale == "ka" else "ru-RU",
                )
                page = context.new_page()
                console_errors: list[str] = []
                failed_requests: list[str] = []
                page.on(
                    "console",
                    lambda msg: console_errors.append(msg.text)
                    if msg.type == "error"
                    else None,
                )
                page.on(
                    "requestfailed",
                    lambda req: failed_requests.append(f"{req.method} {req.url} {req.failure}"),
                )

                def snap(label: str, path: str) -> None:
                    console_errors.clear()
                    failed_requests.clear()
                    shot_name = _slug(label, role, size_name)
                    page.screenshot(path=str(shots / f"{shot_name}.png"), full_page=True)
                    page.screenshot(
                        path=str(shots / f"{shot_name}__viewport.png"),
                        full_page=False,
                    )
                    metrics = page.evaluate(METRIC_JS, vp["width"])
                    report["pages"].append(
                        {
                            "role": role,
                            "size": size_name,
                            "label": label,
                            "path": path,
                            "final_url": page.url,
                            "shot": f"shots/{shot_name}.png",
                            "shot_viewport": f"shots/{shot_name}__viewport.png",
                            "console_errors": list(console_errors),
                            "failed_requests": list(failed_requests),
                            **metrics,
                        }
                    )

                # login page (logged out)
                page.goto(f"{base}/login", wait_until="networkidle")
                snap("login", "/login")

                # Cookie jar via APIRequestContext (form submit alone was flaky under headless).
                login_resp = context.request.post(
                    f"{base}/login",
                    form={"login": role, "password": password},
                    max_redirects=0,
                )
                if login_resp.status not in (200, 302, 303):
                    raise RuntimeError(
                        f"Playwright login failed for {role}: HTTP {login_resp.status}"
                    )

                if locale == "ka":
                    loc_resp = context.request.post(
                        f"{base}/locale",
                        form={"locale": "ka"},
                        max_redirects=5,
                    )
                    if loc_resp.status not in (200, 302, 303):
                        raise RuntimeError(f"locale switch failed: HTTP {loc_resp.status}")

                for label, path in _pages_for(role, ids):
                    page.goto(f"{base}{path}", wait_until="networkidle")
                    page.wait_for_timeout(200)
                    if "/login" in page.url and path != "/login":
                        raise RuntimeError(
                            f"Still on login after auth as {role} for {path} → {page.url}"
                        )
                    snap(label, path)
                context.close()
        browser.close()

    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _compare(before_dir: Path, after_dir: Path, out_path: Path) -> None:
    before = json.loads((before_dir / "report.json").read_text(encoding="utf-8"))
    after = json.loads((after_dir / "report.json").read_text(encoding="utf-8"))

    def key(p: dict[str, Any]) -> tuple[str, str, str]:
        return (p["role"], p["size"], p["label"])

    before_map = {key(p): p for p in before["pages"]}
    after_map = {key(p): p for p in after["pages"]}
    keys = sorted(set(before_map) | set(after_map))

    rows = []
    blocks = []
    for k in keys:
        b = before_map.get(k)
        a = after_map.get(k)
        role, size, label = k
        if not b or not a:
            rows.append(
                f"<tr><td>{escape(role)}</td><td>{escape(size)}</td><td>{escape(label)}</td>"
                f"<td colspan='4'>missing in {'before' if not b else 'after'}</td></tr>"
            )
            continue
        worse_scroll = a["scrollWidth"] > b["scrollWidth"] and a.get("horizontalOverflow")
        worse_tap = a["smallTapCount"] > b["smallTapCount"]
        worse_font = a["smallFontFields"] > b["smallFontFields"]
        worse_clip = a.get("clippedCount", 0) > b.get("clippedCount", 0)
        cls = "worse" if (worse_scroll or worse_tap or worse_font or worse_clip) else ""
        rows.append(
            f"<tr class='{cls}'><td>{escape(role)}</td><td>{escape(size)}</td><td>{escape(label)}</td>"
            f"<td>{b['scrollWidth']} → {a['scrollWidth']}</td>"
            f"<td>{b['smallFontFields']} → {a['smallFontFields']}</td>"
            f"<td>{b['smallTapCount']} → {a['smallTapCount']}</td>"
            f"<td>{b.get('clippedCount', 0)} → {a.get('clippedCount', 0)}</td></tr>"
        )
        if size == "mobile":
            b_full = before_dir / b["shot"]
            a_full = after_dir / a["shot"]
            b_vp = before_dir / b.get("shot_viewport", "")
            a_vp = after_dir / a.get("shot_viewport", "")
            vp_pair = ""
            if b.get("shot_viewport") and a.get("shot_viewport") and b_vp.exists() and a_vp.exists():
                vp_pair = (
                    f"<div class='pair'>"
                    f"<figure><figcaption>before viewport</figcaption>"
                    f"<img src='{escape(b_vp.as_uri())}' /></figure>"
                    f"<figure><figcaption>after viewport</figcaption>"
                    f"<img src='{escape(a_vp.as_uri())}' /></figure>"
                    f"</div>"
                )
            blocks.append(
                f"<section><h3>{escape(role)} / {escape(label)}</h3>"
                f"<div class='pair'>"
                f"<figure><figcaption>before full</figcaption>"
                f"<img src='{escape(b_full.as_uri())}' /></figure>"
                f"<figure><figcaption>after full</figcaption>"
                f"<img src='{escape(a_full.as_uri())}' /></figure>"
                f"</div>{vp_pair}</section>"
            )

    html = f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8" />
<title>UI compare {escape(before_dir.name)} → {escape(after_dir.name)}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 1rem; }}
table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
th, td {{ border: 1px solid #ccc; padding: 4px 8px; text-align: left; }}
tr.worse {{ background: #ffe8e8; }}
.pair {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }}
.pair img {{ max-width: 390px; border: 1px solid #ddd; }}
</style></head><body>
<h1>Compare: {escape(before_dir.name)} → {escape(after_dir.name)}</h1>
<table>
<thead><tr><th>role</th><th>size</th><th>page</th>
<th>scrollWidth</th><th>fields &lt;16px</th><th>tap &lt;44px</th><th>clipped</th></tr></thead>
<tbody>
{''.join(rows)}
</tbody></table>
<h2>Mobile shots</h2>
{''.join(blocks)}
</body></html>
"""
    out_path.write_text(html, encoding="utf-8")


def _start_server(
    db_path: Path, port: int, log_path: Path
) -> tuple[subprocess.Popen[bytes], Any]:
    env = os.environ.copy()
    # Do not inherit a production DATABASE_URL / secrets from the shell/.env for this child:
    # pydantic-settings still reads .env, but process env overrides file values.
    env["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    env["SECRET_KEY"] = "ui-snapshots-secret-key"
    env["APP_ENV"] = "development"
    env["SEED_ADMIN_PASSWORD"] = PASSWORDS["admin"]
    env["SEED_MECHANIC_PASSWORD"] = PASSWORDS["mechanic_batumi"]
    env["SEED_ACCOUNTANT_PASSWORD"] = PASSWORDS["accountant"]
    # Avoid accidental ERP/proxy calls during screenshots
    env["PROXY_API_URL"] = ""
    env["PROXY_API_TOKEN"] = ""

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "wb")  # noqa: SIM115 — closed in main() after process exits
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )
    return proc, log_fh


def main() -> int:
    _require_playwright()
    parser = argparse.ArgumentParser(description="Capture UI snapshots and metrics")
    parser.add_argument("--name", default=_git_branch(), help="Run name under artifacts/ui/")
    parser.add_argument("--compare", default="", help="Other run name to compare against")
    parser.add_argument("--locale", default="", choices=["", "ka"], help="Optional UI locale")
    parser.add_argument("--keep-db", action="store_true", help="Keep temp sqlite under artifacts")
    args = parser.parse_args()

    out_dir = ARTIFACTS / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / "snapshot.db" if args.keep_db else Path(
        __import__("tempfile").mkdtemp(prefix="scerp-ui-")
    ) / "snapshot.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    log_path = out_dir / "server.log"
    proc, log_fh = _start_server(db_path, port, log_path)
    try:
        _wait_http(f"{base}/login")
        # Give seed a moment after first request/startup
        time.sleep(0.5)
        if not db_path.exists():
            # uvicorn may create DB on startup slightly later
            deadline = time.time() + 15
            while time.time() < deadline and not db_path.exists():
                time.sleep(0.2)
        ids = _seed_demo(base, db_path)
        (out_dir / "demo_ids.json").write_text(
            json.dumps(ids, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        report = _capture(
            base=base,
            out_dir=out_dir,
            ids=ids,
            locale=args.locale or None,
        )
        mobile = [p for p in report["pages"] if p["size"] == "mobile"]
        overflow = sum(1 for p in mobile if p.get("horizontalOverflow"))
        clipped = sum(1 for p in mobile if p.get("clippedCount", 0) > 0)
        print(
            f"Wrote {out_dir / 'report.json'} — "
            f"{len(report['pages'])} pages, mobile overflow: {overflow}, "
            f"with clipped: {clipped}"
        )
        if args.compare:
            before = ARTIFACTS / args.compare
            if not (before / "report.json").exists():
                print(f"Compare source missing: {before / 'report.json'}", file=sys.stderr)
                return 1
            compare_path = out_dir / "compare.html"
            _compare(before, out_dir, compare_path)
            print(f"Compare: {compare_path}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        try:
            log_fh.close()
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
