"""Helpers for saving connections with consistent naming and persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlit.domains.connections.domain.config import ConnectionConfig


@dataclass
class SaveConnectionResult:
    config: ConnectionConfig | None
    saved: bool
    message: str
    warning: str | None = None


def is_config_saved(connections: list[ConnectionConfig], config: ConnectionConfig) -> bool:
    for conn in connections:
        if conn.name == config.name:
            return True
        if conn.tcp_endpoint and config.tcp_endpoint:
            if (
                conn.tcp_endpoint.host == config.tcp_endpoint.host
                and conn.tcp_endpoint.database == config.tcp_endpoint.database
            ):
                return True
    return False


def ensure_unique_name(existing: set[str], base_name: str) -> str:
    if base_name and base_name not in existing:
        return base_name
    name = base_name or "Connection"
    counter = 2
    candidate = name
    while candidate in existing:
        candidate = f"{name}-{counter}"
        counter += 1
    return candidate


def save_connection(
    connections: list[ConnectionConfig],
    connection_store: Any,
    config: ConnectionConfig,
) -> SaveConnectionResult:
    existing_names = {c.name for c in connections}
    config.name = ensure_unique_name(existing_names, config.name)
    connections.append(config)

    warning = None
    if not getattr(connection_store, "is_persistent", True):
        warning = "Connections are not persisted in this session"

    try:
        connection_store.save_all(connections)
        return SaveConnectionResult(
            config=config,
            saved=True,
            message=f"Saved '{config.name}'",
            warning=warning,
        )
    except Exception as exc:
        return SaveConnectionResult(
            config=config,
            saved=False,
            message=f"Failed to save: {exc}",
            warning=warning,
        )
