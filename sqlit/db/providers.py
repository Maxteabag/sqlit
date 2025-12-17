"""Canonical provider registry (Plan B).

This module is the single source of truth for:
- supported provider ids (db_type)
- display names and capabilities (via ConnectionSchema)
- adapter classes
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from .adapters.base import DatabaseAdapter
    from .schema import ConnectionSchema


@dataclass(frozen=True)
class ProviderSpec:
    schema_path: tuple[str, str]
    adapter_path: tuple[str, str]


PROVIDERS: dict[str, ProviderSpec] = {
    "mssql": ProviderSpec(
        schema_path=("sqlit.db.schema", "MSSQL_SCHEMA"),
        adapter_path=("sqlit.db.adapters.mssql", "SQLServerAdapter"),
    ),
    "sqlite": ProviderSpec(
        schema_path=("sqlit.db.schema", "SQLITE_SCHEMA"),
        adapter_path=("sqlit.db.adapters.sqlite", "SQLiteAdapter"),
    ),
    "postgresql": ProviderSpec(
        schema_path=("sqlit.db.schema", "POSTGRESQL_SCHEMA"),
        adapter_path=("sqlit.db.adapters.postgresql", "PostgreSQLAdapter"),
    ),
    "mysql": ProviderSpec(
        schema_path=("sqlit.db.schema", "MYSQL_SCHEMA"),
        adapter_path=("sqlit.db.adapters.mysql", "MySQLAdapter"),
    ),
    "oracle": ProviderSpec(
        schema_path=("sqlit.db.schema", "ORACLE_SCHEMA"),
        adapter_path=("sqlit.db.adapters.oracle", "OracleAdapter"),
    ),
    "mariadb": ProviderSpec(
        schema_path=("sqlit.db.schema", "MARIADB_SCHEMA"),
        adapter_path=("sqlit.db.adapters.mariadb", "MariaDBAdapter"),
    ),
    "duckdb": ProviderSpec(
        schema_path=("sqlit.db.schema", "DUCKDB_SCHEMA"),
        adapter_path=("sqlit.db.adapters.duckdb", "DuckDBAdapter"),
    ),
    "cockroachdb": ProviderSpec(
        schema_path=("sqlit.db.schema", "COCKROACHDB_SCHEMA"),
        adapter_path=("sqlit.db.adapters.cockroachdb", "CockroachDBAdapter"),
    ),
    "turso": ProviderSpec(
        schema_path=("sqlit.db.schema", "TURSO_SCHEMA"),
        adapter_path=("sqlit.db.adapters.turso", "TursoAdapter"),
    ),
    "supabase": ProviderSpec(
        schema_path=("sqlit.db.schema", "SUPABASE_SCHEMA"),
        adapter_path=("sqlit.db.adapters.supabase", "SupabaseAdapter"),
    ),
    "d1": ProviderSpec(
        schema_path=("sqlit.db.schema", "D1_SCHEMA"),
        adapter_path=("sqlit.db.adapters.d1", "D1Adapter"),
    ),
}


def get_supported_db_types() -> list[str]:
    return list(PROVIDERS.keys())


def iter_provider_schemas() -> Iterable[ConnectionSchema]:
    return (_get_schema(spec) for spec in PROVIDERS.values())


def get_provider_spec(db_type: str) -> ProviderSpec:
    spec = PROVIDERS.get(db_type)
    if spec is None:
        raise ValueError(f"Unknown database type: {db_type}")
    return spec


def _get_schema(spec: ProviderSpec) -> ConnectionSchema:
    module_name, attr_name = spec.schema_path
    module = import_module(module_name)
    return getattr(module, attr_name)


def get_connection_schema(db_type: str) -> ConnectionSchema:
    return _get_schema(get_provider_spec(db_type))


def get_all_schemas() -> dict[str, ConnectionSchema]:
    return {k: _get_schema(v) for k, v in PROVIDERS.items()}


def get_adapter(db_type: str) -> "DatabaseAdapter":
    adapter = get_adapter_class(db_type)()
    # Internal: allow adapters to know their provider id for test/mocking hooks.
    setattr(adapter, "_db_type", db_type)
    return adapter


def get_adapter_class(db_type: str) -> type["DatabaseAdapter"]:
    spec = get_provider_spec(db_type)
    module_name, class_name = spec.adapter_path
    module = import_module(module_name)
    adapter_cls = getattr(module, class_name)
    return adapter_cls


def get_default_port(db_type: str) -> str:
    spec = PROVIDERS.get(db_type)
    if spec is None:
        return "1433"
    return _get_schema(spec).default_port


def get_display_name(db_type: str) -> str:
    spec = PROVIDERS.get(db_type)
    return _get_schema(spec).display_name if spec else db_type


def supports_ssh(db_type: str) -> bool:
    spec = PROVIDERS.get(db_type)
    return _get_schema(spec).supports_ssh if spec else False


def is_file_based(db_type: str) -> bool:
    spec = PROVIDERS.get(db_type)
    return _get_schema(spec).is_file_based if spec else False


def has_advanced_auth(db_type: str) -> bool:
    spec = PROVIDERS.get(db_type)
    return _get_schema(spec).has_advanced_auth if spec else False
