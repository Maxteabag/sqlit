"""Persistent file cache for Azure SQL access tokens.

Each `sqlit query` invocation otherwise spawns `az account get-access-token`
via azure-identity's AzureCliCredential, which costs ~300ms-1s of CLI
startup. Caching the JWT on disk between invocations makes one-shot queries
roughly as fast as the SQL roundtrip itself.

The token is stored at 0600 under the user's sqlit config dir. Anyone with
read access to that file can impersonate the user against Azure SQL for the
token's remaining lifetime (default 1h) — same tradeoff as caching `az`'s
own MSAL cache, and the same threat surface as `~/.azure/`.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

from sqlit.shared.core.store import CONFIG_DIR

CACHE_FILE = CONFIG_DIR / "azure_sql_token.json"

# Tokens are treated as expired this many seconds before their real expiry,
# so a token acquired here is still good when the ODBC handshake runs.
_REFRESH_BEFORE_EXPIRY = 300


@dataclass(frozen=True)
class CachedToken:
    token: str
    expires_on: int


def load() -> CachedToken | None:
    """Return a cached token if it exists and is comfortably non-expired."""
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    expires_on = int(data.get("expires_on", 0))
    if expires_on <= time.time() + _REFRESH_BEFORE_EXPIRY:
        return None
    token = data.get("token")
    if not isinstance(token, str) or not token:
        return None
    return CachedToken(token=token, expires_on=expires_on)


def save(token: str, expires_on: int) -> None:
    """Persist a token atomically with 0600 perms."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"token": token, "expires_on": int(expires_on)})
    tmp = CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, CACHE_FILE)


def clear() -> None:
    """Remove the cached token if present."""
    try:
        CACHE_FILE.unlink()
    except FileNotFoundError:
        pass
