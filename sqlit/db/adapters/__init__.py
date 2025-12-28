"""Adapter factory and lightweight exports.

Avoid importing every adapter module at import time; adapters are loaded lazily
via the provider registry when requested.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from ..providers import PROVIDERS
from ..providers import get_adapter as _get_adapter
from ..providers import get_supported_db_types as _get_supported_adapter_db_types
from .base import ColumnInfo, DatabaseAdapter, TableInfo

__all__ = [
    "ColumnInfo",
    "DatabaseAdapter",
    "TableInfo",
    # Adapter classes (lazy via __getattr__)
    "ClickHouseAdapter",
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
    "AthenaAdapter",
    # Factory helpers
    "get_adapter",
    "get_supported_adapter_db_types",
]

if TYPE_CHECKING:
    from .clickhouse import ClickHouseAdapter
    from .cockroachdb import CockroachDBAdapter
    from .duckdb import DuckDBAdapter
    from .firebird import FirebirdAdapter
    from .mariadb import MariaDBAdapter
    from .mssql import SQLServerAdapter
    from .mysql import MySQLAdapter
    from .oracle import OracleAdapter
    from .postgresql import PostgreSQLAdapter
    from .sqlite import SQLiteAdapter
    from .supabase import SupabaseAdapter
    from .turso import TursoAdapter
    from .athena import AthenaAdapter


def get_adapter(db_type: str) -> DatabaseAdapter:
    return _get_adapter(db_type)


def get_supported_adapter_db_types() -> list[str]:
    """Return the database types supported by the adapter factory."""
    return _get_supported_adapter_db_types()


_ADAPTER_PATH_BY_NAME: dict[str, tuple[str, str]] | None = None


def __getattr__(name: str) -> type[DatabaseAdapter]:
    global _ADAPTER_PATH_BY_NAME
    if _ADAPTER_PATH_BY_NAME is None:
        _ADAPTER_PATH_BY_NAME = {spec.adapter_path[1]: spec.adapter_path for spec in PROVIDERS.values()}

    adapter_path = _ADAPTER_PATH_BY_NAME.get(name)
    if adapter_path is None:
        raise AttributeError(name)
    module_name, class_name = adapter_path
    module = import_module(module_name)
    return getattr(module, class_name)
