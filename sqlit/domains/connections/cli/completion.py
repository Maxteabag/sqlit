"""Shell-completion helpers for the sqlit CLI.

These run inside the argcomplete completion subprocess on every <Tab> press,
so they must stay cheap: read the connections JSON directly rather than
building the services stack (which imports asyncio and the credentials
service). See ``sqlit.cli`` for where the completers are attached.
"""

from __future__ import annotations

from typing import Any


def _connection_names() -> list[str]:
    """Return saved connection names from the global config, best-effort.

    Reads ``CONFIG_DIR/connections.json`` directly and mirrors the payload
    shape handled by ``ConnectionStore._unpack_connections_payload`` (a bare
    list for the legacy v1 format, or a ``{"connections": [...]}`` dict for
    v2+). Any error returns an empty list — completion must never raise.
    """
    try:
        import json

        from sqlit.shared.core.store import CONFIG_DIR

        path = CONFIG_DIR / "connections.json"
        if not path.is_file():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    if isinstance(data, dict):
        raw = data.get("connections")
    else:
        raw = data
    if not isinstance(raw, list):
        return []

    names: list[str] = []
    for entry in raw:
        if isinstance(entry, dict):
            name = entry.get("name")
            if isinstance(name, str) and name:
                names.append(name)
    return names


def complete_connection_names(prefix: str, **_: Any) -> list[str]:
    """argcomplete completer for arguments that take a saved connection name.

    argcomplete invokes completers with extra keyword arguments (``action``,
    ``parser``, ``parsed_args``); we accept and ignore them.
    """
    return [name for name in _connection_names() if name.startswith(prefix)]
