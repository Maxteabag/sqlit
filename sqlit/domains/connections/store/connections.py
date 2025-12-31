"""Connection store for managing saved database connections."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlit.shared.core.store import CONFIG_DIR, JSONFileStore

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig
    from sqlit.domains.connections.app.credentials import CredentialsService


class ConnectionStore(JSONFileStore):
    """Store for managing saved database connections.

    Connections are stored as a JSON object (versioned) in ~/.sqlit/connections.json.
    Passwords are stored separately in the OS keyring via CredentialsService.
    """

    _CURRENT_VERSION = 2
    _CONNECTIONS_KEY = "connections"
    _VERSION_KEY = "version"

    _instance: ConnectionStore | None = None
    is_persistent: bool = True

    def __init__(self, credentials_service: CredentialsService | None = None) -> None:
        super().__init__(CONFIG_DIR / "connections.json")
        self._credentials_service = credentials_service

    @property
    def credentials_service(self) -> CredentialsService:
        """Get the credentials service (lazy-loaded)."""
        if self._credentials_service is None:
            from sqlit.domains.connections.app.credentials import get_credentials_service

            return get_credentials_service()
        return self._credentials_service

    def set_credentials_service(self, service: CredentialsService) -> None:
        """Override the credentials service instance."""
        self._credentials_service = service

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

    def load_all(self, load_credentials: bool = True) -> list[ConnectionConfig]:
        """Load all saved connections.

        Connections are loaded from JSON, and passwords are retrieved
        from the credentials service (OS keyring).

        Returns:
            List of ConnectionConfig objects, or empty list if none exist.
        """
        from sqlit.domains.connections.domain.config import ConnectionConfig

        data = self._read_json()
        if data is None:
            return []
        version, raw_connections, needs_migration = self._unpack_connections_payload(data)
        try:
            from sqlit.domains.connections.providers.config_service import normalize_connection_config

            configs = []
            for conn in raw_connections:
                if not isinstance(conn, dict):
                    continue
                config = ConnectionConfig.from_dict(conn)
                config = normalize_connection_config(config)
                if load_credentials:
                    # Retrieve passwords from credentials service
                    self._load_credentials(config)
                configs.append(config)
            if needs_migration:
                self._migrate_connections_payload(raw_connections, version)
            return configs
        except (TypeError, KeyError):
            return []

    def _unpack_connections_payload(self, data: object) -> tuple[int, list[dict], bool]:
        if isinstance(data, list):
            return 1, data, True
        if isinstance(data, dict):
            raw_version = data.get(self._VERSION_KEY)
            raw_connections = data.get(self._CONNECTIONS_KEY)
            if isinstance(raw_connections, list):
                version = raw_version if isinstance(raw_version, int) else 1
                return version, raw_connections, version != self._CURRENT_VERSION
        return 0, [], False

    def _wrap_connections_payload(self, connections: list[dict]) -> dict:
        return {
            self._VERSION_KEY: self._CURRENT_VERSION,
            self._CONNECTIONS_KEY: connections,
        }

    def _migrate_connections_payload(self, connections: list[dict], version: int) -> None:
        if version == self._CURRENT_VERSION:
            return
        try:
            self._write_json(self._wrap_connections_payload(connections))
        except Exception:
            # Best-effort migration; loading should still succeed.
            pass

    def _load_credentials(self, config: ConnectionConfig) -> None:
        """Load credentials from the credentials service into config.

        Args:
            config: ConnectionConfig to populate with credentials.
        """
        endpoint = config.tcp_endpoint
        if endpoint and endpoint.password is None:
            password = self.credentials_service.get_password(config.name)
            if password is not None:
                endpoint.password = password

        if config.tunnel and config.tunnel.password is None:
            ssh_password = self.credentials_service.get_ssh_password(config.name)
            if ssh_password is not None:
                config.tunnel.password = ssh_password

    def _save_credentials(self, config: ConnectionConfig) -> None:
        """Save credentials from config to the credentials service.

        Args:
            config: ConnectionConfig containing credentials to save.

        Note: Empty string "" is a valid password (e.g., CockroachDB insecure mode).
              Only None means "delete/no password stored".
        """
        endpoint = config.tcp_endpoint
        if endpoint and endpoint.password is not None:
            self.credentials_service.set_password(config.name, endpoint.password)
        else:
            self.credentials_service.delete_password(config.name)

        if config.tunnel and config.tunnel.password is not None:
            self.credentials_service.set_ssh_password(config.name, config.tunnel.password)
        else:
            self.credentials_service.delete_ssh_password(config.name)

    def _config_to_dict_without_passwords(self, config: ConnectionConfig) -> dict:
        """Convert config to dict without password fields.

        Args:
            config: ConnectionConfig to convert.

        Returns:
            Dict representation with password fields set to None.
            None indicates "load from credentials service on next load".
        """
        return config.to_dict(include_passwords=False)

    def save_all(self, connections: list[ConnectionConfig]) -> None:
        """Save all connections.

        Passwords are stored in the credentials service (OS keyring),
        not in the JSON file.

        Args:
            connections: List of ConnectionConfig objects to save.
        """
        for config in connections:
            self._save_credentials(config)

        payload = [self._config_to_dict_without_passwords(c) for c in connections]
        self._write_json(self._wrap_connections_payload(payload))

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


def load_connections(
    load_credentials: bool = True,
    store: ConnectionStore | None = None,
) -> list[ConnectionConfig]:
    """Load saved connections from config file."""
    store = store or _store
    return store.load_all(load_credentials=load_credentials)


def save_connections(
    connections: list[ConnectionConfig],
    store: ConnectionStore | None = None,
) -> None:
    """Save connections to config file."""
    store = store or _store
    store.save_all(connections)
