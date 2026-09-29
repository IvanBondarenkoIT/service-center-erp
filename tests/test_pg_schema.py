from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not os.environ.get("PG_ADMIN_URL"), reason="PG_ADMIN_URL not set")
def test_app_tables_and_enums_live_in_scerp_schema() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_pg_schema.py"), "--reset"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
