"""Configuration management for sqlit.

This module contains domain types (DatabaseType, AuthType, ConnectionConfig)
and re-exports persistence functions from stores for backward compatibility.

NOTE: This module uses lazy imports for db.providers to avoid loading all
adapter classes at import time. Only _get_supported_db_types is loaded
eagerly (needed to create DatabaseType enum).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

# Only import what's needed to create the DatabaseType enum
from .db.providers import get_supported_db_types as _get_supported_db_types

# Re-export store paths for backward compatibility
from .stores.base import CONFIG_DIR

CONFIG_PATH = CONFIG_DIR / "connections.json"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
HISTORY_PATH = CONFIG_DIR / "query_history.json"
STARRED_PATH = CONFIG_DIR / "starred_queries.json"


# Module-level convenience functions for backward compatibility.
# These are wrappers to avoid import cycles with the store modules.
def load_connections(load_credentials: bool = True) -> list[ConnectionConfig]:
    """Load saved connections from config file."""
    from .stores.connections import load_connections as _load_connections

    return _load_connections(load_credentials=load_credentials)


def save_connections(connections: list[ConnectionConfig]) -> None:
    """Save connections to config file."""
    from .stores.connections import save_connections as _save_connections

    _save_connections(connections)


def load_settings() -> dict:
    """Load app settings from config file."""
    from .stores.settings import load_settings as _load_settings

    return _load_settings()


def save_settings(settings: dict) -> None:
    """Save app settings to config file."""
    from .stores.settings import save_settings as _save_settings

    _save_settings(settings)


def load_query_history(connection_name: str) -> list:
    """Load query history for a specific connection, sorted by most recent first."""
    from .stores.history import load_query_history as _load_query_history

    return _load_query_history(connection_name)


def save_query_to_history(connection_name: str, query: str) -> None:
    """Save a query to history for a connection."""
    from .stores.history import save_query_to_history as _save_query_to_history

    _save_query_to_history(connection_name, query)


def delete_query_from_history(connection_name: str, timestamp: str) -> bool:
    """Delete a specific query from history by connection name and timestamp."""
    from .stores.history import delete_query_from_history as _delete_query_from_history

    return _delete_query_from_history(connection_name, timestamp)


def load_starred_queries(connection_name: str) -> set[str]:
    """Load starred queries for a specific connection."""
    from .stores.starred import load_starred_queries as _load_starred

    return _load_starred(connection_name)


def is_query_starred(connection_name: str, query: str) -> bool:
    """Check if a query is starred."""
    from .stores.starred import is_query_starred as _is_starred

    return _is_starred(connection_name, query)


def toggle_query_star(connection_name: str, query: str) -> bool:
    """Toggle star status. Returns True if now starred."""
    from .stores.starred import toggle_query_star as _toggle

    return _toggle(connection_name, query)


if TYPE_CHECKING:

    class DatabaseType(str, Enum):
        MSSQL = "mssql"
        POSTGRESQL = "postgresql"
        COCKROACHDB = "cockroachdb"
        MYSQL = "mysql"
        MARIADB = "mariadb"
        ORACLE = "oracle"
        SQLITE = "sqlite"
        DUCKDB = "duckdb"
        SUPABASE = "supabase"
        TURSO = "turso"
        D1 = "d1"
        FIREBIRD = "firebird"

else:
    DatabaseType = Enum("DatabaseType", {t.upper(): t for t in _get_supported_db_types()})  # type: ignore[misc]


def get_database_type_labels() -> dict[DatabaseType, str]:
    """Get database type display labels (lazy-loaded)."""
    from .db.providers import get_display_name
    return {db_type: get_display_name(db_type.value) for db_type in DatabaseType}


class AuthType(Enum):
    """Authentication types for SQL Server connections."""

    WINDOWS = "windows"
    SQL_SERVER = "sql"
    AD_PASSWORD = "ad_password"
    AD_INTERACTIVE = "ad_interactive"
    AD_INTEGRATED = "ad_integrated"


AUTH_TYPE_LABELS = {
    AuthType.WINDOWS: "Windows Authentication",
    AuthType.SQL_SERVER: "SQL Server Authentication",
    AuthType.AD_PASSWORD: "Microsoft Entra Password",
    AuthType.AD_INTERACTIVE: "Microsoft Entra MFA",
    AuthType.AD_INTEGRATED: "Microsoft Entra Integrated",
}


def _get_default_driver() -> str:
    """Get default ODBC driver (lazy import)."""
    from .drivers import SUPPORTED_DRIVERS
    return SUPPORTED_DRIVERS[0]


@dataclass
class ConnectionConfig:
    """Database connection configuration."""

    name: str
    db_type: str = "mssql"  # Database type: mssql, sqlite, postgresql, mysql
    # Server-based database fields (SQL Server, PostgreSQL, MySQL)
    server: str = ""
    port: str = ""  # Default derived from schema for server-based databases
    database: str = ""
    username: str = ""
    password: str | None = None
    # SQL Server specific fields
    auth_type: str = "sql"
    driver: str = field(default_factory=_get_default_driver)
    trusted_connection: bool = False
    # SQLite specific fields
    file_path: str = ""
    # SSH tunnel fields
    ssh_enabled: bool = False
    ssh_host: str = ""
    ssh_port: str = "22"
    ssh_username: str = ""
    ssh_auth_type: str = "key"  # "key" or "password"
    ssh_password: str | None = None
    ssh_key_path: str = ""
    # Supabase specific fields
    supabase_region: str = ""
    supabase_project_id: str = ""
    # Oracle specific fields
    oracle_role: str = "normal"  # "normal", "sysdba", "sysoper"
    # Source tracking (e.g., "docker" for auto-detected containers)
    source: str | None = None
    # Original connection URL if created from URL
    connection_url: str | None = None
    # Extra options from URL query parameters (e.g., sslmode=require)
    extra_options: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Handle backwards compatibility with old configs."""
        # Old configs without db_type are SQL Server
        if not hasattr(self, "db_type") or not self.db_type:
            self.db_type = "mssql"

        # Apply default port for server-based DBs if missing (lazy import)
        if not getattr(self, "port", None):
            from .db.providers import get_default_port
            default_port = get_default_port(self.db_type)
            if default_port:
                self.port = default_port

        # Handle old SQL Server auth compatibility
        if self.db_type == "mssql":
            if self.auth_type == "windows" and not self.trusted_connection and self.username:
                self.auth_type = "sql"

    def get_db_type(self) -> DatabaseType:
        """Get the DatabaseType enum value."""
        try:
            return DatabaseType(self.db_type)
        except ValueError:
            return DatabaseType.MSSQL  # type: ignore[attr-defined, no-any-return]

    def get_auth_type(self) -> AuthType:
        """Get the AuthType enum value."""
        try:
            return AuthType(self.auth_type)
        except ValueError:
            return AuthType.SQL_SERVER

    def get_connection_string(self) -> str:
        """Build the connection string for SQL Server.

        .. deprecated::
            This method is deprecated. Connection string building is now
            handled internally by SQLServerAdapter._build_connection_string().
            Use SQLServerAdapter.connect() directly instead.
        """
        import warnings

        warnings.warn(
            "ConnectionConfig.get_connection_string() is deprecated. "
            "Connection string building is now handled internally by SQLServerAdapter.",
            DeprecationWarning,
            stacklevel=2,
        )

        if self.db_type != "mssql":
            raise ValueError("get_connection_string() is only for SQL Server connections")

        server_with_port = self.server
        if self.port and self.port != "1433":
            server_with_port = f"{self.server},{self.port}"

        base = (
            f"DRIVER={{{self.driver}}};"
            f"SERVER={server_with_port};"
            f"DATABASE={self.database or 'master'};"
            f"TrustServerCertificate=yes;"
        )

        auth = self.get_auth_type()

        if auth == AuthType.WINDOWS:
            return base + "Trusted_Connection=yes;"
        elif auth == AuthType.SQL_SERVER:
            return base + f"UID={self.username};PWD={self.password};"
        elif auth == AuthType.AD_PASSWORD:
            return base + f"Authentication=ActiveDirectoryPassword;" f"UID={self.username};PWD={self.password};"
        elif auth == AuthType.AD_INTERACTIVE:
            return base + f"Authentication=ActiveDirectoryInteractive;" f"UID={self.username};"
        elif auth == AuthType.AD_INTEGRATED:
            return base + "Authentication=ActiveDirectoryIntegrated;"

        return base + "Trusted_Connection=yes;"

    def get_display_info(self) -> str:
        """Get a display string for the connection."""
        from .db.providers import is_file_based
        if is_file_based(self.db_type):
            return self.file_path or self.name

        if self.db_type == "supabase":
            return f"{self.name} ({self.supabase_region})"

        db_part = f"@{self.database}" if self.database else ""
        return f"{self.name}{db_part}"

    def get_source_emoji(self) -> str:
        """Get emoji indicator for connection source (e.g., '🐳 ' for docker)."""
        return get_source_emoji(self.source)


# Source emoji mapping
SOURCE_EMOJIS: dict[str, str] = {
    "docker": "🐳 ",
}


def get_source_emoji(source: str | None) -> str:
    """Get emoji for a connection source.

    Args:
        source: The source type (e.g., "docker") or None.

    Returns:
        Emoji string with trailing space, or empty string if no emoji.
    """
    if source is None:
        return ""
    return SOURCE_EMOJIS.get(source, "")
