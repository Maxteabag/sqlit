"""Canonical provider registry (Plan B).

This module is the single source of truth for:
- supported provider ids (db_type)
- display names and capabilities (via ConnectionSchema)
- adapter classes
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .adapters.base import DatabaseAdapter
from .adapters.cockroachdb import CockroachDBAdapter
from .adapters.d1 import D1Adapter
from .adapters.duckdb import DuckDBAdapter
from .adapters.mariadb import MariaDBAdapter
from .adapters.mssql import SQLServerAdapter
from .adapters.mysql import MySQLAdapter
from .adapters.oracle import OracleAdapter
from .adapters.postgresql import PostgreSQLAdapter
from .adapters.sqlite import SQLiteAdapter
from .adapters.supabase import SupabaseAdapter
from .adapters.turso import TursoAdapter
from .schema import (
    COCKROACHDB_SCHEMA,
    D1_SCHEMA,
    DUCKDB_SCHEMA,
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

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True)
class ProviderSpec:
    schema: ConnectionSchema
    adapter_cls: type[DatabaseAdapter]


PROVIDERS: dict[str, ProviderSpec] = {
    "mssql": ProviderSpec(schema=MSSQL_SCHEMA, adapter_cls=SQLServerAdapter),
    "sqlite": ProviderSpec(schema=SQLITE_SCHEMA, adapter_cls=SQLiteAdapter),
    "postgresql": ProviderSpec(schema=POSTGRESQL_SCHEMA, adapter_cls=PostgreSQLAdapter),
    "mysql": ProviderSpec(schema=MYSQL_SCHEMA, adapter_cls=MySQLAdapter),
    "oracle": ProviderSpec(schema=ORACLE_SCHEMA, adapter_cls=OracleAdapter),
    "mariadb": ProviderSpec(schema=MARIADB_SCHEMA, adapter_cls=MariaDBAdapter),
    "duckdb": ProviderSpec(schema=DUCKDB_SCHEMA, adapter_cls=DuckDBAdapter),
    "cockroachdb": ProviderSpec(schema=COCKROACHDB_SCHEMA, adapter_cls=CockroachDBAdapter),
    "turso": ProviderSpec(schema=TURSO_SCHEMA, adapter_cls=TursoAdapter),
    "supabase": ProviderSpec(schema=SUPABASE_SCHEMA, adapter_cls=SupabaseAdapter),
    "d1": ProviderSpec(schema=D1_SCHEMA, adapter_cls=D1Adapter),
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


def get_adapter(db_type: str) -> DatabaseAdapter:
    adapter = get_provider_spec(db_type).adapter_cls()
    # Internal: allow adapters to know their provider id for test/mocking hooks.
    setattr(adapter, "_db_type", db_type)
    return adapter


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
