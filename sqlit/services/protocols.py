"""Protocols for dependency injection in sqlit services.

This module defines Protocol classes that allow for dependency injection
and easier testing of the services layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..config import ConnectionConfig


@runtime_checkable
class AdapterProtocol(Protocol):
    """Protocol for database adapters.

    This protocol defines the minimal interface required by QueryService
    to execute queries against a database.
    """

    def connect(self, config: ConnectionConfig) -> Any:
        """Connect to the database.

        Args:
            config: Connection configuration.

        Returns:
            A database connection object.
        """
        ...

    def execute_query(self, conn: Any, query: str, max_rows: int | None = None) -> tuple[list[str], list[tuple], bool]:
        """Execute a SELECT-type query.

        Args:
            conn: Database connection.
            query: SQL query string.
            max_rows: Optional maximum rows to fetch.

        Returns:
            Tuple of (columns, rows, truncated).
        """
        ...

    def execute_non_query(self, conn: Any, query: str) -> int:
        """Execute a non-SELECT query.

        Args:
            conn: Database connection.
            query: SQL query string.

        Returns:
            Number of rows affected.
        """
        ...


@runtime_checkable
class AdapterFactoryProtocol(Protocol):
    """Protocol for adapter factory functions.

    This protocol defines the interface for functions that create
    database adapters based on database type.
    """

    def __call__(self, db_type: str) -> AdapterProtocol:
        """Create an adapter for the given database type.

        Args:
            db_type: Database type string (e.g., 'mssql', 'postgresql').

        Returns:
            A database adapter instance.
        """
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
    """Protocol for connection storage.

    This protocol defines the interface for storing and retrieving
    database connection configurations.
    """

    def load(self) -> list[ConnectionConfig]:
        """Load all saved connections.

        Returns:
            List of connection configurations.
        """
        ...

    def save(self, connections: list[ConnectionConfig]) -> None:
        """Save connections.

        Args:
            connections: List of connection configurations to save.
        """
        ...


@runtime_checkable
class SettingsStoreProtocol(Protocol):
    """Protocol for settings storage.

    This protocol defines the interface for storing and retrieving
    application settings.
    """

    def load(self) -> dict:
        """Load settings.

        Returns:
            Settings dictionary.
        """
        ...

    def save(self, settings: dict) -> None:
        """Save settings.

        Args:
            settings: Settings dictionary to save.
        """
        ...
