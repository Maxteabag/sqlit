"""Configuration management for sqlit.

This module contains domain types (DatabaseType, AuthType, ConnectionConfig)
and re-exports persistence functions from stores for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from .db.providers import (
    get_default_port as _get_default_port,
)
from .db.providers import (
    get_display_name as _provider_display_name,
)
from .db.providers import (
    get_supported_db_types as _get_supported_db_types,
)
from .db.providers import (
    is_file_based as _is_file_based,
)
from .drivers import SUPPORTED_DRIVERS

# Re-export store paths and persistence helpers for backward compatibility
from .stores.base import CONFIG_DIR

CONFIG_PATH = CONFIG_DIR / "connections.json"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
HISTORY_PATH = CONFIG_DIR / "query_history.json"


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

else:
    DatabaseType = Enum("DatabaseType", {t.upper(): t for t in _get_supported_db_types()})  # type: ignore[misc]


DATABASE_TYPE_LABELS = {db_type: _provider_display_name(db_type.value) for db_type in DatabaseType}


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
    password: str = ""
    # SQL Server specific fields
    auth_type: str = "sql"
    driver: str = SUPPORTED_DRIVERS[0]
    trusted_connection: bool = False  # Legacy field for backwards compatibility
    # SQLite specific fields
    file_path: str = ""
    # SSH tunnel fields
    ssh_enabled: bool = False
    ssh_host: str = ""
    ssh_port: str = "22"
    ssh_username: str = ""
    ssh_auth_type: str = "key"  # "key" or "password"
    ssh_password: str = ""
    ssh_key_path: str = ""
    # Supabase specific fields
    supabase_region: str = ""
    supabase_project_id: str = ""

    def __post_init__(self) -> None:
        """Handle backwards compatibility with old configs."""
        # Old configs without db_type are SQL Server
        if not hasattr(self, "db_type") or not self.db_type:
            self.db_type = "mssql"

        # Apply default port for server-based DBs if missing
        default_port = _get_default_port(self.db_type)
        if not getattr(self, "port", None) and default_port:
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
        if _is_file_based(self.db_type):
            return self.file_path or self.name

        if self.db_type == "supabase":
            return f"{self.name} ({self.supabase_region})"

        db_part = f"@{self.database}" if self.database else ""
        return f"{self.name}{db_part}"
