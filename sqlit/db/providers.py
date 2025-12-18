"""Canonical provider registry.

This module is the single source of truth for:
- supported provider ids (db_type)
- display names and capabilities (via ConnectionSchema)
- adapter classes
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

# Pre-import all schemas (no external dependencies)
from .schema import (
    CLICKHOUSE_SCHEMA,
    COCKROACHDB_SCHEMA,
    D1_SCHEMA,
    DUCKDB_SCHEMA,
    FIREBIRD_SCHEMA,
    MARIADB_SCHEMA,
    MSSQL_SCHEMA,
    MYSQL_SCHEMA,
    ORACLE_SCHEMA,
    POSTGRESQL_SCHEMA,
    SQLITE_SCHEMA,
    SUPABASE_SCHEMA,
    TURSO_SCHEMA,
    ConnectionSchema,
)

# Pre-import all adapter classes (they lazy-load their dependencies internally)
from .adapters.clickhouse import ClickHouseAdapter
from .adapters.cockroachdb import CockroachDBAdapter
from .adapters.d1 import D1Adapter
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

if TYPE_CHECKING:
    from .adapters.base import DatabaseAdapter


@dataclass(frozen=True)
class ProviderSpec:
    schema: ConnectionSchema
    adapter_class: type["DatabaseAdapter"]


PROVIDERS: dict[str, ProviderSpec] = {
    "mssql": ProviderSpec(schema=MSSQL_SCHEMA, adapter_class=SQLServerAdapter),
    "sqlite": ProviderSpec(schema=SQLITE_SCHEMA, adapter_class=SQLiteAdapter),
    "postgresql": ProviderSpec(schema=POSTGRESQL_SCHEMA, adapter_class=PostgreSQLAdapter),
    "mysql": ProviderSpec(schema=MYSQL_SCHEMA, adapter_class=MySQLAdapter),
    "oracle": ProviderSpec(schema=ORACLE_SCHEMA, adapter_class=OracleAdapter),
    "mariadb": ProviderSpec(schema=MARIADB_SCHEMA, adapter_class=MariaDBAdapter),
    "duckdb": ProviderSpec(schema=DUCKDB_SCHEMA, adapter_class=DuckDBAdapter),
    "cockroachdb": ProviderSpec(schema=COCKROACHDB_SCHEMA, adapter_class=CockroachDBAdapter),
    "turso": ProviderSpec(schema=TURSO_SCHEMA, adapter_class=TursoAdapter),
    "supabase": ProviderSpec(schema=SUPABASE_SCHEMA, adapter_class=SupabaseAdapter),
    "d1": ProviderSpec(schema=D1_SCHEMA, adapter_class=D1Adapter),
    "clickhouse": ProviderSpec(schema=CLICKHOUSE_SCHEMA, adapter_class=ClickHouseAdapter),
    "firebird": ProviderSpec(schema=FIREBIRD_SCHEMA, adapter_class=FirebirdAdapter),
}


def get_supported_db_types() -> list[str]:
    return list(PROVIDERS.keys())


def iter_provider_schemas() -> Iterable[ConnectionSchema]:
    return (spec.schema for spec in PROVIDERS.values())


def get_provider_spec(db_type: str) -> ProviderSpec:
    spec = PROVIDERS.get(db_type)
    if spec is None:
        raise ValueError(f"Unknown database type: {db_type}")
    return spec


def get_connection_schema(db_type: str) -> ConnectionSchema:
    return get_provider_spec(db_type).schema


def get_all_schemas() -> dict[str, ConnectionSchema]:
    return {k: v.schema for k, v in PROVIDERS.items()}


def _check_mock_missing_driver(db_type: str, adapter: "DatabaseAdapter") -> None:
    """Check if driver should be mocked as missing (for testing).

    This is external to the adapter class to avoid the base class
    needing to know about concrete implementation identities.
    """
    import os

    forced_missing = os.environ.get("SQLIT_MOCK_MISSING_DRIVERS", "").strip()
    if not forced_missing:
        return

    forced = {s.strip() for s in forced_missing.split(",") if s.strip()}
    if db_type in forced:
        from .exceptions import MissingDriverError

        if not adapter.install_extra or not adapter.install_package:
            raise ImportError(f"Missing driver for {adapter.name}")
        raise MissingDriverError(adapter.name, adapter.install_extra, adapter.install_package)


def get_adapter(db_type: str) -> "DatabaseAdapter":
    adapter = get_adapter_class(db_type)()
    _check_mock_missing_driver(db_type, adapter)
    return adapter


def get_adapter_class(db_type: str) -> type["DatabaseAdapter"]:
    return get_provider_spec(db_type).adapter_class


def get_default_port(db_type: str) -> str:
    spec = PROVIDERS.get(db_type)
    if spec is None:
        return "1433"
    return spec.schema.default_port


def get_display_name(db_type: str) -> str:
    spec = PROVIDERS.get(db_type)
    return spec.schema.display_name if spec else db_type


def supports_ssh(db_type: str) -> bool:
    spec = PROVIDERS.get(db_type)
    return spec.schema.supports_ssh if spec else False


def is_file_based(db_type: str) -> bool:
    spec = PROVIDERS.get(db_type)
    return spec.schema.is_file_based if spec else False


def has_advanced_auth(db_type: str) -> bool:
    spec = PROVIDERS.get(db_type)
    return spec.schema.has_advanced_auth if spec else False


def requires_auth(db_type: str) -> bool:
    """Check if this database type requires authentication."""
    spec = PROVIDERS.get(db_type)
    return spec.schema.requires_auth if spec else True
