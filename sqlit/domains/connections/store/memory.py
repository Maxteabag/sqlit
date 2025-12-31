"""In-memory connection store for tests and mock mode."""

from __future__ import annotations

import copy

from sqlit.domains.connections.domain.config import ConnectionConfig


class InMemoryConnectionStore:
    """Connection store that keeps data in memory only."""

    is_persistent: bool = False

    def __init__(self, connections: list[ConnectionConfig] | None = None) -> None:
        self._connections = copy.deepcopy(connections or [])

    def load_all(self, load_credentials: bool = True) -> list[ConnectionConfig]:
        return copy.deepcopy(self._connections)

    def save_all(self, connections: list[ConnectionConfig]) -> None:
        self._connections = copy.deepcopy(connections)

    def get_by_name(self, name: str) -> ConnectionConfig | None:
        for conn in self._connections:
            if conn.name == name:
                return copy.deepcopy(conn)
        return None

    def add(self, connection: ConnectionConfig) -> None:
        if any(c.name == connection.name for c in self._connections):
            raise ValueError(f"Connection '{connection.name}' already exists")
        self._connections.append(copy.deepcopy(connection))

    def delete(self, name: str) -> bool:
        original_count = len(self._connections)
        self._connections = [c for c in self._connections if c.name != name]
        return len(self._connections) < original_count

    def set_connections(self, connections: list[ConnectionConfig]) -> None:
        self._connections = copy.deepcopy(connections)
