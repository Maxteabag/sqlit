"""Database adapters for sqlit - abstraction layer for different database types.

This module re-exports from sqlit.db for backward compatibility.
New code should import directly from sqlit.db or sqlit.db.adapters.
"""

# Re-export everything from the new location for backward compatibility
from .db import (
    CockroachDBAdapter,
    ColumnInfo,
    DatabaseAdapter,
    DuckDBAdapter,
    MariaDBAdapter,
    MySQLAdapter,
    OracleAdapter,
    PostgreSQLAdapter,
    SQLiteAdapter,
    SQLServerAdapter,
    create_ssh_tunnel,
    get_adapter,
)

__all__ = [
    # Base
    "ColumnInfo",
    "DatabaseAdapter",
    # Adapters
    "CockroachDBAdapter",
    "DuckDBAdapter",
    "MariaDBAdapter",
    "MySQLAdapter",
    "OracleAdapter",
    "PostgreSQLAdapter",
    "SQLiteAdapter",
    "SQLServerAdapter",
    # Factory
    "get_adapter",
    # Tunnel
    "create_ssh_tunnel",
]
