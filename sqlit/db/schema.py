"""Connection schema definitions for database types.

This module provides pure metadata about connection parameters for each
database type, decoupled from UI concerns. The UI layer transforms these
schemas into form widgets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class FieldType(Enum):
    TEXT = "text"
    PASSWORD = "password"
    SELECT = "select"
    DROPDOWN = "dropdown"
    FILE = "file"


@dataclass(frozen=True)
class SelectOption:
    """An option for a select field."""

    value: str
    label: str


@dataclass(frozen=True)
class SchemaField:
    name: str
    label: str
    field_type: FieldType = FieldType.TEXT
    required: bool = False
    default: str = ""
    placeholder: str = ""
    description: str = ""
    options: tuple[SelectOption, ...] = ()
    visible_when: Callable[[dict], bool] | None = None
    group: str | None = None
    advanced: bool = False


@dataclass(frozen=True)
class ConnectionSchema:
    db_type: str
    display_name: str
    fields: tuple[SchemaField, ...]
    supports_ssh: bool = True


# Common field templates
def _server_field(placeholder: str = "localhost") -> SchemaField:
    return SchemaField(
        name="server",
        label="Server",
        placeholder=placeholder,
        required=True,
        group="server_port",
    )


def _port_field(default: str) -> SchemaField:
    return SchemaField(
        name="port",
        label="Port",
        placeholder=default,
        default=default,
        group="server_port",
    )


def _database_field(placeholder: str = "(empty = browse all)", required: bool = False) -> SchemaField:
    return SchemaField(
        name="database",
        label="Database",
        placeholder=placeholder,
        required=required,
    )


def _username_field(required: bool = True) -> SchemaField:
    return SchemaField(
        name="username",
        label="Username",
        placeholder="username",
        required=required,
        group="credentials",
    )


def _password_field() -> SchemaField:
    return SchemaField(
        name="password",
        label="Password",
        field_type=FieldType.PASSWORD,
        group="credentials",
    )


def _file_path_field(placeholder: str) -> SchemaField:
    return SchemaField(
        name="file_path",
        label="Database File",
        field_type=FieldType.FILE,
        placeholder=placeholder,
        required=True,
    )


# Schema definitions for each database type

def _get_mssql_driver_options() -> tuple[SelectOption, ...]:
    """Get available ODBC driver options for SQL Server."""
    # These are checked at runtime in the UI layer
    return (
        SelectOption("ODBC Driver 18 for SQL Server", "ODBC Driver 18 for SQL Server"),
        SelectOption("ODBC Driver 17 for SQL Server", "ODBC Driver 17 for SQL Server"),
        SelectOption("ODBC Driver 13 for SQL Server", "ODBC Driver 13 for SQL Server"),
    )


def _get_mssql_auth_options() -> tuple[SelectOption, ...]:
    """Get authentication type options for SQL Server."""
    return (
        SelectOption("sql", "SQL Server Authentication"),
        SelectOption("windows", "Windows Authentication"),
        SelectOption("ad_password", "Azure AD Password"),
        SelectOption("ad_interactive", "Azure AD Interactive"),
        SelectOption("ad_integrated", "Azure AD Integrated"),
    )


# Auth types that need username
_MSSQL_AUTH_NEEDS_USERNAME = {"sql", "ad_password", "ad_interactive"}
# Auth types that need password
_MSSQL_AUTH_NEEDS_PASSWORD = {"sql", "ad_password"}


MSSQL_SCHEMA = ConnectionSchema(
    db_type="mssql",
    display_name="SQL Server",
    fields=(
        SchemaField(
            name="server",
            label="Server",
            placeholder="server\\instance",
            required=True,
            group="server_port",
        ),
        _port_field("1433"),
        _database_field(),
        SchemaField(
            name="driver",
            label="Driver",
            field_type=FieldType.SELECT,
            options=_get_mssql_driver_options(),
            default="ODBC Driver 18 for SQL Server",
            advanced=True,
        ),
        SchemaField(
            name="auth_type",
            label="Authentication",
            field_type=FieldType.DROPDOWN,
            options=_get_mssql_auth_options(),
            default="sql",
        ),
        SchemaField(
            name="username",
            label="Username",
            required=True,
            group="credentials",
            visible_when=lambda v: v.get("auth_type") in _MSSQL_AUTH_NEEDS_USERNAME,
        ),
        SchemaField(
            name="password",
            label="Password",
            field_type=FieldType.PASSWORD,
            group="credentials",
            visible_when=lambda v: v.get("auth_type") in _MSSQL_AUTH_NEEDS_PASSWORD,
        ),
    ),
)

POSTGRESQL_SCHEMA = ConnectionSchema(
    db_type="postgresql",
    display_name="PostgreSQL",
    fields=(
        _server_field(),
        _port_field("5432"),
        _database_field(),
        _username_field(),
        _password_field(),
    ),
)

MYSQL_SCHEMA = ConnectionSchema(
    db_type="mysql",
    display_name="MySQL",
    fields=(
        _server_field(),
        _port_field("3306"),
        _database_field(),
        _username_field(),
        _password_field(),
    ),
)

MARIADB_SCHEMA = ConnectionSchema(
    db_type="mariadb",
    display_name="MariaDB",
    fields=(
        _server_field(),
        _port_field("3306"),
        _database_field(),
        _username_field(),
        _password_field(),
    ),
)

ORACLE_SCHEMA = ConnectionSchema(
    db_type="oracle",
    display_name="Oracle",
    fields=(
        SchemaField(
            name="server",
            label="Host",
            placeholder="localhost",
            required=True,
            group="server_port",
        ),
        _port_field("1521"),
        SchemaField(
            name="database",
            label="Service Name",
            placeholder="ORCL or XEPDB1",
            required=True,
        ),
        _username_field(),
        _password_field(),
    ),
)

COCKROACHDB_SCHEMA = ConnectionSchema(
    db_type="cockroachdb",
    display_name="CockroachDB",
    fields=(
        _server_field(),
        _port_field("26257"),
        _database_field(),
        _username_field(),
        _password_field(),
    ),
)

SQLITE_SCHEMA = ConnectionSchema(
    db_type="sqlite",
    display_name="SQLite",
    fields=(
        _file_path_field("/path/to/database.db"),
    ),
    supports_ssh=False,
)

DUCKDB_SCHEMA = ConnectionSchema(
    db_type="duckdb",
    display_name="DuckDB",
    fields=(
        _file_path_field("/path/to/database.duckdb"),
    ),
    supports_ssh=False,
)

TURSO_SCHEMA = ConnectionSchema(
    db_type="turso",
    display_name="Turso",
    fields=(
        SchemaField(
            name="server",
            label="Database URL",
            placeholder="your-db-name.turso.io",
            required=True,
            description="Turso database URL (without libsql:// prefix)",
        ),
        SchemaField(
            name="password",
            label="Auth Token",
            field_type=FieldType.PASSWORD,
            required=False,
            description="Database authentication token, optional for local servers",
        ),
    ),
    supports_ssh=False,  # Turso uses HTTPS, SSH tunneling not applicable
)


def _get_supabase_region_options() -> tuple[SelectOption, ...]:
    regions = (
        "us-east-1",
        "us-east-2",
        "us-west-1",
        "us-west-2",
        "ca-central-1",
        "sa-east-1",
        "eu-west-1",
        "eu-west-2",
        "eu-west-3",
        "eu-central-1",
        "eu-central-2",
        "eu-north-1",
        "ap-south-1",
        "ap-southeast-1",
        "ap-southeast-2",
        "ap-northeast-1",
        "ap-northeast-2",
    )
    return tuple(SelectOption(r, r) for r in regions)


SUPABASE_SCHEMA = ConnectionSchema(
    db_type="supabase",
    display_name="Supabase",
    fields=(
        SchemaField(
            name="supabase_region",
            label="Region",
            field_type=FieldType.DROPDOWN,
            options=_get_supabase_region_options(),
            required=True,
            default="us-east-1",
        ),
        SchemaField(
            name="supabase_project_id",
            label="Project ID",
            placeholder="abcdefghijklmnop",
            required=True,
        ),
        SchemaField(
            name="password",
            label="Password",
            field_type=FieldType.PASSWORD,
            required=True,
        ),
    ),
    supports_ssh=False,
)


# Schema registry
_SCHEMAS: dict[str, ConnectionSchema] = {
    "mssql": MSSQL_SCHEMA,
    "postgresql": POSTGRESQL_SCHEMA,
    "mysql": MYSQL_SCHEMA,
    "mariadb": MARIADB_SCHEMA,
    "oracle": ORACLE_SCHEMA,
    "cockroachdb": COCKROACHDB_SCHEMA,
    "sqlite": SQLITE_SCHEMA,
    "duckdb": DUCKDB_SCHEMA,
    "turso": TURSO_SCHEMA,
    "supabase": SUPABASE_SCHEMA,
}


def get_connection_schema(db_type: str) -> ConnectionSchema:
    """Get the connection schema for a database type.

    Args:
        db_type: Database type identifier (e.g., "postgresql", "mysql")

    Returns:
        ConnectionSchema for the database type

    Raises:
        ValueError: If db_type is not recognized
    """
    schema = _SCHEMAS.get(db_type)
    if schema is None:
        raise ValueError(f"Unknown database type: {db_type}")
    return schema


def get_all_schemas() -> dict[str, ConnectionSchema]:
    """Get all registered connection schemas."""
    return dict(_SCHEMAS)


def get_supported_db_types() -> list[str]:
    """Get list of supported database type identifiers."""
    return list(_SCHEMAS.keys())
