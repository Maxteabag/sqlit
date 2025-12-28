"""Configuration management for sqlit.

This module contains domain types (DatabaseType, AuthType, ConnectionConfig)
and re-exports persistence functions from stores for backward compatibility.

NOTE: This module uses lazy imports for db.providers to avoid loading all
adapter classes at import time. Only _get_supported_db_types is loaded
eagerly (needed to create DatabaseType enum).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import Enum
from typing import TYPE_CHECKING, Any, Mapping

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
        SNOWFLAKE = "snowflake"

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
    AD_DEFAULT = "ad_default"  # Uses Azure CLI / environment credentials


AUTH_TYPE_LABELS = {
    AuthType.WINDOWS: "Windows Authentication",
    AuthType.SQL_SERVER: "SQL Server Authentication",
    AuthType.AD_PASSWORD: "Microsoft Entra Password",
    AuthType.AD_INTERACTIVE: "Microsoft Entra MFA",
    AuthType.AD_INTEGRATED: "Microsoft Entra Integrated",
    AuthType.AD_DEFAULT: "Microsoft Entra Default (CLI)",
}


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
    # SSH tunnel fields
    ssh_enabled: bool = False
    ssh_host: str = ""
    ssh_port: str = "22"
    ssh_username: str = ""
    ssh_auth_type: str = "key"  # "key" or "password"
    ssh_password: str | None = None
    ssh_key_path: str = ""
    # Source tracking (e.g., "docker" for auto-detected containers)
    source: str | None = None
    # Original connection URL if created from URL
    connection_url: str | None = None
    # Extra options from URL query parameters (e.g., sslmode=require)
    extra_options: dict[str, str] = field(default_factory=dict)
    # Provider-specific options (auth_type, driver, file_path, etc.)
    options: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ConnectionConfig:
        """Create a ConnectionConfig from a dict, with legacy key support."""
        payload = dict(data)

        if "host" in payload and "server" not in payload:
            payload["server"] = payload.pop("host")

        db_type = payload.get("db_type")
        if not isinstance(db_type, str) or not db_type:
            payload["db_type"] = "mssql"

        raw_options = payload.pop("options", None)
        options: dict[str, Any] = {}
        if isinstance(raw_options, dict):
            options.update(raw_options)

        base_fields = {f.name for f in fields(cls)}
        for key in list(payload.keys()):
            if key in base_fields:
                continue
            if key not in options:
                options[key] = payload.pop(key)
            else:
                payload.pop(key)

        payload["options"] = options
        return cls(**payload)

    def get_option(self, name: str, default: Any | None = None) -> Any:
        return self.options.get(name, default)

    def set_option(self, name: str, value: Any) -> None:
        self.options[name] = value

    def get_field_value(self, name: str, default: Any = "") -> Any:
        if name in self.__dataclass_fields__:
            value = getattr(self, name)
            return value if value is not None else default
        return self.options.get(name, default)

    def get_db_type(self) -> DatabaseType:
        """Get the DatabaseType enum value."""
        try:
            return DatabaseType(self.db_type)
        except ValueError:
            return DatabaseType.MSSQL  # type: ignore[attr-defined, no-any-return]

    def get_source_emoji(self) -> str:
        """Get emoji indicator for connection source (e.g., '🐳 ' for docker)."""
        return get_source_emoji(self.source)


# Source emoji mapping
SOURCE_EMOJIS: dict[str, str] = {
    "docker": "🐳 ",
    "azure": "☁️ ",
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
