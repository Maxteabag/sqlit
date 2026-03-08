"""Helpers for persisting connection dialog state across restarts."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any


def get_restart_cache_path() -> Path:
    """Return the cache path used for restart state."""
    return Path(tempfile.gettempdir()) / "sqlit-driver-install-restore.json"


def write_restart_cache(payload: dict[str, Any]) -> None:
    """Persist restart cache payload to disk (best effort)."""
    try:
        get_restart_cache_path().write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        # Best-effort; don't block installation due to caching failure.
        pass


def clear_restart_cache() -> None:
    """Remove restart cache file if it exists."""
    try:
        get_restart_cache_path().unlink(missing_ok=True)
    except Exception:
        pass


def write_pending_connection_cache(connection_name: str) -> None:
    """Cache a pending connection name for auto-reconnect after driver install restart.

    This is used when a user tries to connect to a server but the driver is missing.
    After the driver is installed and the app restarts, it can auto-connect to this
    connection.
    """
    payload = {
        "version": 2,
        "type": "pending_connection",
        "connection_name": connection_name,
    }
    write_restart_cache(payload)
