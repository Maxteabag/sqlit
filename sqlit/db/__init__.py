"""Database abstraction layer for sqlit."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

from .adapters.base import ColumnInfo, DatabaseAdapter, TableInfo
from .providers import (
    get_adapter,
    get_default_port,
    get_display_name,
    get_supported_db_types,
    has_advanced_auth,
    is_file_based,
    supports_ssh,
)
from .tunnel import create_ssh_tunnel, ensure_ssh_tunnel_available

__all__ = [
    # Base
    "ColumnInfo",
    "DatabaseAdapter",
    "TableInfo",
    # Factory / providers
    "get_adapter",
    "get_default_port",
    "get_display_name",
    "get_supported_db_types",
    "has_advanced_auth",
    "is_file_based",
    "supports_ssh",
    # UI schema (lazy wrappers)
    "ConnectionSchema",
    "FieldType",
    "SchemaField",
    "SelectOption",
    "get_all_schemas",
    "get_connection_schema",
    # Adapters (lazy via __getattr__)
    "CockroachDBAdapter",
    "DuckDBAdapter",
    "FirebirdAdapter",
    "MariaDBAdapter",
    "MySQLAdapter",
    "OracleAdapter",
    "PostgreSQLAdapter",
    "SQLiteAdapter",
    "SQLServerAdapter",
    "SupabaseAdapter",
    "TursoAdapter",
    # Tunnel
    "create_ssh_tunnel",
    "ensure_ssh_tunnel_available",
]

if TYPE_CHECKING:
    from .adapters.cockroachdb import CockroachDBAdapter
    from .adapters.duckdb import DuckDBAdapter
    from .adapters.firebird import FirebirdAdapter
    from .adapters.mariadb import MariaDBAdapter
    from .adapters.mssql import SQLServerAdapter
    from .adapters.mysql import MySQLAdapter
    from .adapters.oracle import OracleAdapter
    from .adapters.postgresql import PostgreSQLAdapter
    from .adapters.sqlite import SQLiteAdapter
    from .adapters.supabase import SupabaseAdapter
    from .adapters.turso import TursoAdapter
    from .schema import ConnectionSchema, FieldType, SchemaField, SelectOption


def get_connection_schema(db_type: str) -> Any:
    from .schema import get_connection_schema as _get_connection_schema

    return _get_connection_schema(db_type)


def get_all_schemas() -> Any:
    from .schema import get_all_schemas as _get_all_schemas

    return _get_all_schemas()


_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    # Schema types
    "ConnectionSchema": ("sqlit.db.schema", "ConnectionSchema"),
    "FieldType": ("sqlit.db.schema", "FieldType"),
    "SchemaField": ("sqlit.db.schema", "SchemaField"),
    "SelectOption": ("sqlit.db.schema", "SelectOption"),
    # Adapters (through sqlit.db.adapters, which itself lazy-loads)
    "AzureSQLAdapter": ("sqlit.db.adapters", "AzureSQLAdapter"),
    "CockroachDBAdapter": ("sqlit.db.adapters", "CockroachDBAdapter"),
    "DuckDBAdapter": ("sqlit.db.adapters", "DuckDBAdapter"),
    "FirebirdAdapter": ("sqlit.db.adapters", "FirebirdAdapter"),
    "MariaDBAdapter": ("sqlit.db.adapters", "MariaDBAdapter"),
    "MySQLAdapter": ("sqlit.db.adapters", "MySQLAdapter"),
    "OracleAdapter": ("sqlit.db.adapters", "OracleAdapter"),
    "PostgreSQLAdapter": ("sqlit.db.adapters", "PostgreSQLAdapter"),
    "SQLiteAdapter": ("sqlit.db.adapters", "SQLiteAdapter"),
    "SQLServerAdapter": ("sqlit.db.adapters", "SQLServerAdapter"),
    "SupabaseAdapter": ("sqlit.db.adapters", "SupabaseAdapter"),
    "TursoAdapter": ("sqlit.db.adapters", "TursoAdapter"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_ATTRS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attr_name = target
    module = import_module(module_name)
    return getattr(module, attr_name)
