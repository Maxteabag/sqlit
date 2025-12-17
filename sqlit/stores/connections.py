"""Connection store for managing saved database connections."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import CONFIG_DIR, JSONFileStore

if TYPE_CHECKING:
    from ..config import ConnectionConfig
    from ..services.credentials import CredentialsService


class ConnectionStore(JSONFileStore):
    """Store for managing saved database connections.

    Connections are stored as a JSON array in ~/.sqlit/connections.json.
    Passwords are stored separately in the OS keyring via CredentialsService.
    """

    _instance: ConnectionStore | None = None

    def __init__(self, credentials_service: CredentialsService | None = None) -> None:
        super().__init__(CONFIG_DIR / "connections.json")
        self._credentials_service = credentials_service

    @property
    def credentials_service(self) -> CredentialsService:
        """Get the credentials service (lazy-loaded)."""
        if self._credentials_service is None:
            from ..services.credentials import get_credentials_service

            return get_credentials_service()
        return self._credentials_service

    @classmethod
    def get_instance(cls) -> ConnectionStore:
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (useful for testing)."""
        cls._instance = None

    def load_all(self) -> list[ConnectionConfig]:
        """Load all saved connections.

        Connections are loaded from JSON, and passwords are retrieved
        from the credentials service (OS keyring).

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

            configs = []
            for conn in migrated:
                config = ConnectionConfig(**conn)
                # Retrieve passwords from credentials service
                self._load_credentials(config)
                configs.append(config)
            return configs
        except (TypeError, KeyError):
            return []

    def _load_credentials(self, config: ConnectionConfig) -> None:
        """Load credentials from the credentials service into config.

        Args:
            config: ConnectionConfig to populate with credentials.
        """
        if not config.password:
            password = self.credentials_service.get_password(config.name)
            if password:
                config.password = password

        if not config.ssh_password:
            ssh_password = self.credentials_service.get_ssh_password(config.name)
            if ssh_password:
                config.ssh_password = ssh_password

    def _save_credentials(self, config: ConnectionConfig) -> None:
        """Save credentials from config to the credentials service.

        Args:
            config: ConnectionConfig containing credentials to save.
        """
        if config.password:
            self.credentials_service.set_password(config.name, config.password)
        else:
            self.credentials_service.delete_password(config.name)

        if config.ssh_password:
            self.credentials_service.set_ssh_password(config.name, config.ssh_password)
        else:
            self.credentials_service.delete_ssh_password(config.name)

    def _config_to_dict_without_passwords(self, config: ConnectionConfig) -> dict:
        """Convert config to dict without password fields.

        Args:
            config: ConnectionConfig to convert.

        Returns:
            Dict representation without password and ssh_password.
        """
        data = vars(config).copy()
        data["password"] = ""
        data["ssh_password"] = ""
        return data

    def save_all(self, connections: list[ConnectionConfig]) -> None:
        """Save all connections.

        Passwords are stored in the credentials service (OS keyring),
        not in the JSON file.

        Args:
            connections: List of ConnectionConfig objects to save.
        """
        for config in connections:
            self._save_credentials(config)

        self._write_json([self._config_to_dict_without_passwords(c) for c in connections])

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

        Also deletes associated credentials from the keyring.

        Args:
            name: Connection name to delete.

        Returns:
            True if deleted, False if not found.
        """
        connections = self.load_all()
        original_count = len(connections)
        connections = [c for c in connections if c.name != name]
        if len(connections) < original_count:
            # Delete credentials from keyring
            self.credentials_service.delete_all_for_connection(name)
            self.save_all(connections)
            return True
        return False

    def list_names(self) -> list[str]:
        """Get list of all connection names.

        Returns:
            List of connection names.
        """
        return [c.name for c in self.load_all()]


_store = ConnectionStore()


def load_connections() -> list[ConnectionConfig]:
    """Load saved connections from config file."""
    return _store.load_all()


def save_connections(connections: list[ConnectionConfig]) -> None:
    """Save connections to config file."""
    _store.save_all(connections)
