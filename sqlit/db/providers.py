"""Canonical provider registry.

This module is the single source of truth for:
- supported provider ids (db_type)
- display names and capabilities (via ConnectionSchema)
- adapter classes
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from importlib import import_module
from typing import TYPE_CHECKING

# Pre-import all schemas (no external dependencies)
from .schema import (
    ATHENA_SCHEMA,
    BIGQUERY_SCHEMA,
    CLICKHOUSE_SCHEMA,
    COCKROACHDB_SCHEMA,
    D1_SCHEMA,
    DUCKDB_SCHEMA,
    FIREBIRD_SCHEMA,
    FLIGHT_SCHEMA,
    MARIADB_SCHEMA,
    MSSQL_SCHEMA,
    MYSQL_SCHEMA,
    ORACLE_SCHEMA,
    POSTGRESQL_SCHEMA,
    REDSHIFT_SCHEMA,
    SNOWFLAKE_SCHEMA,
    SQLITE_SCHEMA,
    SUPABASE_SCHEMA,
    TURSO_SCHEMA,
    ConnectionSchema,
)

if TYPE_CHECKING:
    from ..config import ConnectionConfig
    from .adapters.base import DatabaseAdapter


@dataclass(frozen=True)
class ProviderSpec:
    schema: ConnectionSchema
    adapter_path: tuple[str, str]


PROVIDERS: dict[str, ProviderSpec] = {
    "mssql": ProviderSpec(
        schema=MSSQL_SCHEMA,
        adapter_path=("sqlit.db.adapters.mssql", "SQLServerAdapter"),
    ),
    "sqlite": ProviderSpec(
        schema=SQLITE_SCHEMA,
        adapter_path=("sqlit.db.adapters.sqlite", "SQLiteAdapter"),
    ),
    "postgresql": ProviderSpec(
        schema=POSTGRESQL_SCHEMA,
        adapter_path=("sqlit.db.adapters.postgresql", "PostgreSQLAdapter"),
    ),
    "mysql": ProviderSpec(
        schema=MYSQL_SCHEMA,
        adapter_path=("sqlit.db.adapters.mysql", "MySQLAdapter"),
    ),
    "oracle": ProviderSpec(
        schema=ORACLE_SCHEMA,
        adapter_path=("sqlit.db.adapters.oracle", "OracleAdapter"),
    ),
    "mariadb": ProviderSpec(
        schema=MARIADB_SCHEMA,
        adapter_path=("sqlit.db.adapters.mariadb", "MariaDBAdapter"),
    ),
    "duckdb": ProviderSpec(
        schema=DUCKDB_SCHEMA,
        adapter_path=("sqlit.db.adapters.duckdb", "DuckDBAdapter"),
    ),
    "cockroachdb": ProviderSpec(
        schema=COCKROACHDB_SCHEMA,
        adapter_path=("sqlit.db.adapters.cockroachdb", "CockroachDBAdapter"),
    ),
    "turso": ProviderSpec(
        schema=TURSO_SCHEMA,
        adapter_path=("sqlit.db.adapters.turso", "TursoAdapter"),
    ),
    "supabase": ProviderSpec(
        schema=SUPABASE_SCHEMA,
        adapter_path=("sqlit.db.adapters.supabase", "SupabaseAdapter"),
    ),
    "d1": ProviderSpec(
        schema=D1_SCHEMA,
        adapter_path=("sqlit.db.adapters.d1", "D1Adapter"),
    ),
    "clickhouse": ProviderSpec(
        schema=CLICKHOUSE_SCHEMA,
        adapter_path=("sqlit.db.adapters.clickhouse", "ClickHouseAdapter"),
    ),
    "firebird": ProviderSpec(
        schema=FIREBIRD_SCHEMA,
        adapter_path=("sqlit.db.adapters.firebird", "FirebirdAdapter"),
    ),
    "snowflake": ProviderSpec(
        schema=SNOWFLAKE_SCHEMA,
        adapter_path=("sqlit.db.adapters.snowflake", "SnowflakeAdapter"),
    ),
    "athena": ProviderSpec(
        schema=ATHENA_SCHEMA,
        adapter_path=("sqlit.db.adapters.athena", "AthenaAdapter"),
    ),
    "redshift": ProviderSpec(
        schema=REDSHIFT_SCHEMA,
        adapter_path=("sqlit.db.adapters.redshift", "RedshiftAdapter"),
    ),
    "bigquery": ProviderSpec(
        schema=BIGQUERY_SCHEMA,
        adapter_path=("sqlit.db.adapters.bigquery", "BigQueryAdapter"),
    ),
    "flight": ProviderSpec(
        schema=FLIGHT_SCHEMA,
        adapter_path=("sqlit.db.adapters.flight", "FlightSQLAdapter"),
    ),
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


@lru_cache(maxsize=1)
def _get_url_scheme_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for db_type in PROVIDERS:
        adapter_class = get_adapter_class(db_type)
        for scheme in adapter_class.url_schemes():
            mapping[scheme] = db_type
    return mapping


def get_url_scheme_map() -> dict[str, str]:
    return dict(_get_url_scheme_map())


def get_db_type_for_scheme(scheme: str) -> str | None:
    return _get_url_scheme_map().get(scheme.lower())


def get_supported_url_schemes() -> set[str]:
    return set(_get_url_scheme_map().keys())


def _apply_schema_defaults(config: "ConnectionConfig", schema: ConnectionSchema) -> "ConnectionConfig":
    if (
        not config.port
        and schema.default_port
        and any(field.name == "port" for field in schema.fields)
    ):
        config.port = schema.default_port
    return config


def normalize_connection_config(config: "ConnectionConfig") -> "ConnectionConfig":
    """Normalize provider-specific defaults and run adapter validation."""
    try:
        schema = get_connection_schema(config.db_type)
    except ValueError:
        return config

    config = _apply_schema_defaults(config, schema)
    adapter = get_adapter_class(config.db_type)()
    config = adapter.normalize_config(config)
    adapter.validate_config(config)
    return config


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
    module_name, class_name = get_provider_spec(db_type).adapter_path
    return _load_adapter_class(module_name, class_name)


@lru_cache(maxsize=None)
def _load_adapter_class(module_name: str, class_name: str) -> type["DatabaseAdapter"]:
    module = import_module(module_name)
    adapter_class = getattr(module, class_name, None)
    if not isinstance(adapter_class, type):
        raise ImportError(f"Adapter class '{class_name}' not found in {module_name}")
    return adapter_class


def get_default_port(db_type: str) -> str:
    spec = PROVIDERS.get(db_type)
    if spec is None:
        return "1433"
    return spec.schema.default_port


def get_display_name(db_type: str) -> str:
    spec = PROVIDERS.get(db_type)
    return spec.schema.display_name if spec else db_type


def get_badge_label(db_type: str) -> str:
    try:
        adapter_class = get_adapter_class(db_type)
    except ValueError:
        return db_type.upper() if db_type else "DB"
    return adapter_class.badge_label()


def get_connection_display_info(config: "ConnectionConfig") -> str:
    """Return a human-friendly label for a connection."""
    try:
        adapter_class = get_adapter_class(config.db_type)
    except ValueError:
        return config.name
    return adapter_class().get_display_info(config)


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


def requires_database_selection(db_type: str) -> bool:
    """Check if this database type requires a database to be specified.

    Returns True for databases that don't support cross-database queries
    (e.g., PostgreSQL, CockroachDB, D1) where each database is isolated.
    """
    try:
        adapter = get_adapter_class(db_type)()
        return not adapter.supports_cross_database_queries
    except (ValueError, ImportError):
        return False


def validate_database_required(db_type: str, database: str | None) -> None:
    """Validate that a database is specified when required.

    Raises ValueError if the database type requires a database selection
    but none is provided.
    """
    if requires_database_selection(db_type) and not database:
        display_name = get_display_name(db_type)
        raise ValueError(
            f"{display_name} requires a database to be specified. "
            f"Each database is isolated and cross-database queries are not supported."
        )
