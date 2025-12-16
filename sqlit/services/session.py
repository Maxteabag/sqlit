"""Connection session management for sqlit.

This module provides a ConnectionSession class that owns the lifecycle
of database connections and SSH tunnels, ensuring proper cleanup.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..config import ConnectionConfig
    from ..db import DatabaseAdapter
    from .executor import DatabaseExecutor


class ConnectionSession:
    """A database connection session with automatic cleanup.

    This class encapsulates a database connection and optional SSH tunnel,
    providing context manager support for guaranteed resource cleanup.

    Usage:
        with ConnectionSession.create(config) as session:
            result = session.adapter.execute_query(session.connection, query)

    Or for long-lived connections (like in the TUI):
        session = ConnectionSession.create(config)
        # ... use session ...
        session.close()  # Must be called explicitly

    Attributes:
        connection: The raw database connection object.
        adapter: The database adapter for this connection.
        config: The original connection configuration.
        has_tunnel: Whether this session has an active SSH tunnel.
    """

    def __init__(
        self,
        connection: Any,
        adapter: DatabaseAdapter,
        config: ConnectionConfig,
        tunnel: Any | None = None,
    ):
        """Initialize a connection session.

        Args:
            connection: The database connection object.
            adapter: The database adapter instance.
            config: The connection configuration.
            tunnel: Optional SSH tunnel object.
        """
        self._connection = connection
        self._adapter = adapter
        self._config = config
        self._tunnel = tunnel
        self._closed = False
        self._executor: DatabaseExecutor | None = None

    @classmethod
    def create(
        cls,
        config: ConnectionConfig,
        adapter_factory: Callable[[str], DatabaseAdapter] | None = None,
        tunnel_factory: Callable[[ConnectionConfig], tuple[Any, str, int]] | None = None,
    ) -> ConnectionSession:
        """Create a new connection session.

        This factory method handles SSH tunnel creation (if enabled) and
        establishes the database connection.

        Args:
            config: Connection configuration.
            adapter_factory: Optional factory for creating adapters.
                Defaults to get_adapter from sqlit.db.
            tunnel_factory: Optional factory for creating SSH tunnels.
                Defaults to create_ssh_tunnel from sqlit.db.

        Returns:
            A new ConnectionSession instance.

        Raises:
            ValueError: If SSH key file is not found.
            ImportError: If required database driver is not installed.
            Any database-specific connection errors.
        """
        from ..db import create_ssh_tunnel, get_adapter

        get_adapter_fn = adapter_factory or get_adapter
        create_tunnel_fn = tunnel_factory or create_ssh_tunnel

        tunnel, host, port = create_tunnel_fn(config)

        # Adjust config for tunnel if created
        if tunnel:
            connect_config = replace(config, server=host, port=str(port))
        else:
            connect_config = config

        # Get adapter and connect
        adapter = get_adapter_fn(config.db_type)
        connection = adapter.connect(connect_config)

        return cls(connection, adapter, config, tunnel)

    @property
    def connection(self) -> Any:
        """Get the raw database connection object."""
        return self._connection

    @property
    def adapter(self) -> DatabaseAdapter:
        """Get the database adapter."""
        return self._adapter

    @property
    def config(self) -> ConnectionConfig:
        """Get the connection configuration."""
        return self._config

    @property
    def tunnel(self) -> Any | None:
        """Get the SSH tunnel object if present."""
        return self._tunnel

    @property
    def has_tunnel(self) -> bool:
        """Check if this session has an active SSH tunnel."""
        return self._tunnel is not None

    @property
    def is_closed(self) -> bool:
        """Check if this session has been closed."""
        return self._closed

    @property
    def executor(self) -> DatabaseExecutor:
        """Get or create the database executor for serialized operations.

        The executor is lazily created on first access. All database operations
        should go through this executor to ensure thread-safe access.

        Returns:
            The DatabaseExecutor for this session.

        Raises:
            RuntimeError: If the session has been closed.
        """
        if self._closed:
            raise RuntimeError("Cannot get executor for closed session")
        if self._executor is None:
            from .executor import DatabaseExecutor

            self._executor = DatabaseExecutor(self)
        return self._executor

    def close(self) -> None:
        """Close the session and release all resources.

        This method is idempotent - calling it multiple times is safe.
        It shuts down the executor first (to stop pending operations),
        then closes the database connection, then stops the SSH tunnel.
        Exceptions during cleanup are silently caught to ensure all
        resources are released.
        """
        if self._closed:
            return

        # Shutdown executor first (don't wait for pending operations)
        if self._executor is not None:
            try:
                self._executor.shutdown(wait=False)
            except Exception:
                pass
            self._executor = None

        # Close database connection
        if self._connection is not None:
            try:
                close_fn = getattr(self._connection, "close", None)
                if callable(close_fn):
                    close_fn()
            except Exception:
                pass
            self._connection = None

        # Stop SSH tunnel
        if self._tunnel is not None:
            try:
                self._tunnel.stop()
            except Exception:
                pass
            self._tunnel = None

        self._closed = True

    def __enter__(self) -> ConnectionSession:
        """Enter the context manager."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the context manager, ensuring cleanup."""
        self.close()

    def __del__(self) -> None:
        """Destructor to catch unclosed sessions (best-effort cleanup)."""
        if not self._closed:
            self.close()
