"""Configuration management for sqlit.

This module contains domain types (DatabaseType, AuthType, ConnectionConfig)
and re-exports persistence functions from stores for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# Re-export store paths for backward compatibility
from .stores.base import CONFIG_DIR

CONFIG_PATH = CONFIG_DIR / "connections.json"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
HISTORY_PATH = CONFIG_DIR / "query_history.json"

# Re-export persistence functions from stores
from .stores.connections import load_connections, save_connections
from .stores.history import (
    QueryHistoryEntry,
    delete_query_from_history,
    load_query_history,
    save_query_to_history,
)
from .stores.settings import load_settings, save_settings


class DatabaseType(Enum):
    """Supported database types."""

    MSSQL = "mssql"
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    ORACLE = "oracle"
    MARIADB = "mariadb"
    DUCKDB = "duckdb"
    COCKROACHDB = "cockroachdb"
    TURSO = "turso"
    SUPABASE = "supabase"


DATABASE_TYPE_LABELS = {
    DatabaseType.MSSQL: "SQL Server",
    DatabaseType.SQLITE: "SQLite",
    DatabaseType.POSTGRESQL: "PostgreSQL",
    DatabaseType.MYSQL: "MySQL",
    DatabaseType.ORACLE: "Oracle",
    DatabaseType.MARIADB: "MariaDB",
    DatabaseType.DUCKDB: "DuckDB",
    DatabaseType.COCKROACHDB: "CockroachDB",
    DatabaseType.TURSO: "Turso",
    DatabaseType.SUPABASE: "Supabase",
}


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
    port: str = "1433"  # Default varies: 1433 (MSSQL), 5432 (PostgreSQL), 3306 (MySQL)
    database: str = ""
    username: str = ""
    password: str = ""
    # SQL Server specific fields
    auth_type: str = "sql"
    driver: str = "ODBC Driver 18 for SQL Server"
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

    def __post_init__(self):
        """Handle backwards compatibility with old configs."""
        # Old configs without db_type are SQL Server
        if not hasattr(self, "db_type") or not self.db_type:
            self.db_type = "mssql"
        # Handle old SQL Server auth compatibility
        if self.db_type == "mssql":
            if self.auth_type == "windows" and not self.trusted_connection and self.username:
                self.auth_type = "sql"

    def get_db_type(self) -> DatabaseType:
        """Get the DatabaseType enum value."""
        try:
            return DatabaseType(self.db_type)
        except ValueError:
            return DatabaseType.MSSQL

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
            return (
                base
                + f"Authentication=ActiveDirectoryPassword;"
                f"UID={self.username};PWD={self.password};"
            )
        elif auth == AuthType.AD_INTERACTIVE:
            return (
                base + f"Authentication=ActiveDirectoryInteractive;" f"UID={self.username};"
            )
        elif auth == AuthType.AD_INTEGRATED:
            return base + "Authentication=ActiveDirectoryIntegrated;"

        return base + "Trusted_Connection=yes;"

    def get_display_info(self) -> str:
        """Get a display string for the connection."""
        if self.db_type in ("sqlite", "duckdb"):
            return self.file_path or self.name

        if self.db_type == "supabase":
            return f"{self.name} ({self.supabase_region})"

        db_part = f"@{self.database}" if self.database else ""
        return f"{self.name}{db_part}"
