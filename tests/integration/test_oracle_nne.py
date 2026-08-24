"""Real Thin/Thick connection checks against an NNE-required Oracle server."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

_CONNECT_SCRIPT = r"""
import os
import sys
import oracledb

if sys.argv[1] == "thick":
    oracledb.init_oracle_client(lib_dir=os.environ["ORACLE_CLIENT_LIB_DIR"])

connection = oracledb.connect(
    user=os.environ.get("ORACLE_USER", "testuser"),
    password=os.environ.get("ORACLE_PASSWORD", "TestPassword123!"),
    dsn=(
        f"{os.environ.get('ORACLE_HOST', '127.0.0.1')}:"
        f"{os.environ.get('ORACLE_PORT', '1521')}/"
        f"{os.environ.get('ORACLE_SERVICE', 'FREEPDB1')}"
    ),
)
value = connection.cursor().execute("SELECT 1 FROM dual").fetchone()[0]
print(f"mode={'thin' if connection.thin else 'thick'} value={value}")
connection.close()
"""


def _connect(mode: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _CONNECT_SCRIPT, mode],
        text=True,
        capture_output=True,
        env=os.environ.copy(),
        check=False,
        timeout=30,
    )


@pytest.mark.integration
def test_thin_mode_is_rejected_when_native_encryption_is_required() -> None:
    result = _connect("thin")

    assert result.returncode != 0
    assert "DPY-3001" in result.stderr


@pytest.mark.integration
def test_thick_mode_connects_with_instant_client() -> None:
    if not os.environ.get("ORACLE_CLIENT_LIB_DIR"):
        pytest.skip("Oracle Instant Client is not configured")

    result = _connect("thick")

    assert result.returncode == 0, result.stderr
    assert "mode=thick value=1" in result.stdout
