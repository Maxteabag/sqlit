"""Protocols for dependency injection in sqlit services.

This module defines Protocol classes that allow for dependency injection
and easier testing of the services layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


@runtime_checkable
class QueryExecutorProtocol(Protocol):
    """Protocol for executing queries against a database connection."""

    def execute_query(self, conn: Any, query: str, max_rows: int | None = None) -> tuple[list[str], list[tuple], bool]:
        ...

    def execute_non_query(self, conn: Any, query: str) -> int:
        ...


@runtime_checkable
class ProviderFactoryProtocol(Protocol):
    """Protocol for provider factory functions."""

    def __call__(self, db_type: str) -> Any:
        ...


@runtime_checkable
class HistoryStoreProtocol(Protocol):
    """Protocol for query history storage.

    This protocol defines the interface for storing and retrieving
    query history.
    """

    def save_query(self, connection_name: str, query: str) -> None:
        """Save a query to history.

        Args:
            connection_name: Name of the connection.
            query: The SQL query string.
        """
        ...

    def load_for_connection(self, connection_name: str) -> list:
        """Load query history for a connection.

        Args:
            connection_name: Name of the connection.

        Returns:
            List of query history entries.
        """
        ...


@runtime_checkable
class TunnelFactoryProtocol(Protocol):
    """Protocol for SSH tunnel factory functions.

    This protocol defines the interface for functions that create
    SSH tunnels for database connections.
    """

    def __call__(self, config: ConnectionConfig) -> tuple[Any, str, int]:
        """Create an SSH tunnel if enabled in config.

        Args:
            config: Connection configuration.

        Returns:
            Tuple of (tunnel_object, host, port).
            If SSH is not enabled, tunnel_object is None.
        """
        ...


@runtime_checkable
class ConnectionStoreProtocol(Protocol):
    """Protocol for connection storage."""

    is_persistent: bool

    def load_all(self, load_credentials: bool = True) -> list[ConnectionConfig]:
        """Load all saved connections."""
        ...

    def save_all(self, connections: list[ConnectionConfig]) -> None:
        """Save connections."""
        ...


@runtime_checkable
class SettingsStoreProtocol(Protocol):
    """Protocol for settings storage."""

    def load_all(self) -> dict:
        """Load settings."""
        ...

    def save_all(self, settings: dict) -> None:
        """Save settings."""
        ...
