"""Connection store for managing saved database connections."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import CONFIG_DIR, JSONFileStore

if TYPE_CHECKING:
    from ..config import ConnectionConfig


class ConnectionStore(JSONFileStore):
    """Store for managing saved database connections.

    Connections are stored as a JSON array in ~/.sqlit/connections.json
    """

    _instance: ConnectionStore | None = None

    def __init__(self) -> None:
        super().__init__(CONFIG_DIR / "connections.json")

    @classmethod
    def get_instance(cls) -> ConnectionStore:
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load_all(self) -> list[ConnectionConfig]:
        """Load all saved connections.

        Returns:
            List of ConnectionConfig objects, or empty list if none exist.
        """
        from ..config import ConnectionConfig

        data = self._read_json()
        if data is None:
            return []
        try:
            migrated = []
            for conn in data:
                if isinstance(conn, dict) and "host" in conn and "server" not in conn:
                    conn = {**conn, "server": conn.get("host", "")}
                    conn.pop("host", None)
                migrated.append(conn)
            return [ConnectionConfig(**conn) for conn in migrated]
        except (TypeError, KeyError):
            return []

    def save_all(self, connections: list[ConnectionConfig]) -> None:
        """Save all connections.

        Args:
            connections: List of ConnectionConfig objects to save.
        """
        self._write_json([vars(c) for c in connections])

    def get_by_name(self, name: str) -> ConnectionConfig | None:
        """Get a connection by name.

        Args:
            name: Connection name to find.

        Returns:
            ConnectionConfig if found, None otherwise.
        """
        for conn in self.load_all():
            if conn.name == name:
                return conn
        return None

    def add(self, connection: ConnectionConfig) -> None:
        """Add a new connection.

        Args:
            connection: ConnectionConfig to add.

        Raises:
            ValueError: If a connection with the same name already exists.
        """
        connections = self.load_all()
        if any(c.name == connection.name for c in connections):
            raise ValueError(f"Connection '{connection.name}' already exists")
        connections.append(connection)
        self.save_all(connections)

    def update(self, connection: ConnectionConfig) -> None:
        """Update an existing connection.

        Args:
            connection: ConnectionConfig with updated values.

        Raises:
            ValueError: If connection doesn't exist.
        """
        connections = self.load_all()
        for i, c in enumerate(connections):
            if c.name == connection.name:
                connections[i] = connection
                self.save_all(connections)
                return
        raise ValueError(f"Connection '{connection.name}' not found")

    def delete(self, name: str) -> bool:
        """Delete a connection by name.

        Args:
            name: Connection name to delete.

        Returns:
            True if deleted, False if not found.
        """
        connections = self.load_all()
        original_count = len(connections)
        connections = [c for c in connections if c.name != name]
        if len(connections) < original_count:
            self.save_all(connections)
            return True
        return False

    def list_names(self) -> list[str]:
        """Get list of all connection names.

        Returns:
            List of connection names.
        """
        return [c.name for c in self.load_all()]


# Module-level convenience functions for backward compatibility
_store = ConnectionStore()


def load_connections() -> list[ConnectionConfig]:
    """Load saved connections from config file."""
    return _store.load_all()


def save_connections(connections: list[ConnectionConfig]) -> None:
    """Save connections to config file."""
    _store.save_all(connections)
