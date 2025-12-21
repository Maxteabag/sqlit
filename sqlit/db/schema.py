"""Connection schema definitions for database types.

This module defines UI-facing connection metadata (fields + labels + defaults).
The canonical provider registry is `sqlit.db.providers.PROVIDERS`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from ..drivers import SUPPORTED_DRIVERS


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
    tab: str = "general"


@dataclass(frozen=True)
class ConnectionSchema:
    db_type: str
    display_name: str
    fields: tuple[SchemaField, ...]
    supports_ssh: bool = True
    is_file_based: bool = False
    has_advanced_auth: bool = False
    default_port: str = ""
    requires_auth: bool = True  # Whether this database requires authentication


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
        placeholder="(empty = ask every connect)",
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


def _ssh_enabled(v: dict) -> bool:
    return v.get("ssh_enabled") == "enabled"


def _ssh_auth_is_key(v: dict) -> bool:
    return _ssh_enabled(v) and v.get("ssh_auth_type") == "key"


def _ssh_auth_is_password(v: dict) -> bool:
    return _ssh_enabled(v) and v.get("ssh_auth_type") == "password"


def _get_ssh_fields() -> tuple[SchemaField, ...]:
    return (
        SchemaField(
            name="ssh_enabled",
            label="Tunnel",
            field_type=FieldType.SELECT,
            options=(
                SelectOption("disabled", "Disabled"),
                SelectOption("enabled", "Enabled"),
            ),
            default="disabled",
            tab="ssh",
        ),
        SchemaField(
            name="ssh_host",
            label="Host",
            placeholder="bastion.example.com",
            required=True,
            visible_when=_ssh_enabled,
            tab="ssh",
        ),
        SchemaField(
            name="ssh_port",
            label="Port",
            placeholder="22",
            default="22",
            visible_when=_ssh_enabled,
            tab="ssh",
        ),
        SchemaField(
            name="ssh_username",
            label="Username",
            placeholder="ubuntu",
            required=True,
            visible_when=_ssh_enabled,
            tab="ssh",
        ),
        SchemaField(
            name="ssh_auth_type",
            label="Auth",
            field_type=FieldType.SELECT,
            options=(
                SelectOption("key", "Key File"),
                SelectOption("password", "Password"),
            ),
            default="key",
            visible_when=_ssh_enabled,
            tab="ssh",
        ),
        SchemaField(
            name="ssh_key_path",
            label="Key Path",
            field_type=FieldType.FILE,
            placeholder="~/.ssh/id_rsa",
            default="~/.ssh/id_rsa",
            visible_when=_ssh_auth_is_key,
            tab="ssh",
        ),
        SchemaField(
            name="ssh_password",
            label="Password",
            field_type=FieldType.PASSWORD,
            placeholder="(empty = ask every connect)",
            visible_when=_ssh_auth_is_password,
            tab="ssh",
        ),
    )


SSH_FIELDS = _get_ssh_fields()


def _get_mssql_driver_options() -> tuple[SelectOption, ...]:
    return tuple(SelectOption(d, d) for d in SUPPORTED_DRIVERS)


def _get_mssql_auth_options() -> tuple[SelectOption, ...]:
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
            default=SUPPORTED_DRIVERS[0],
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
            placeholder="(empty = ask every connect)",
            group="credentials",
            visible_when=lambda v: v.get("auth_type") in _MSSQL_AUTH_NEEDS_PASSWORD,
        ),
    )
    + SSH_FIELDS,
    has_advanced_auth=True,
    default_port="1433",
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
    )
    + SSH_FIELDS,
    default_port="5432",
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
    )
    + SSH_FIELDS,
    default_port="3306",
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
    )
    + SSH_FIELDS,
    default_port="3306",
)

def _get_oracle_role_options() -> tuple[SelectOption, ...]:
    return (
        SelectOption("normal", "Normal"),
        SelectOption("sysdba", "SYSDBA"),
        SelectOption("sysoper", "SYSOPER"),
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
        SchemaField(
            name="oracle_role",
            label="Role",
            field_type=FieldType.DROPDOWN,
            options=_get_oracle_role_options(),
            default="normal",
        ),
    )
    + SSH_FIELDS,
    default_port="1521",
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
    )
    + SSH_FIELDS,
    default_port="26257",
    requires_auth=False,  # CockroachDB can run in insecure mode without auth
)

SQLITE_SCHEMA = ConnectionSchema(
    db_type="sqlite",
    display_name="SQLite",
    fields=(_file_path_field("/path/to/database.db"),),
    supports_ssh=False,
    is_file_based=True,
)

DUCKDB_SCHEMA = ConnectionSchema(
    db_type="duckdb",
    display_name="DuckDB",
    fields=(_file_path_field("/path/to/database.duckdb"),),
    supports_ssh=False,
    is_file_based=True,
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
            placeholder="auth token (optional)",
            description="Database authentication token, optional for local servers",
        ),
    ),
    supports_ssh=False,
    requires_auth=False,  # Turso local servers don't require auth
)


D1_SCHEMA = ConnectionSchema(
    db_type="d1",
    display_name="Cloudflare D1",
    fields=(
        SchemaField(
            name="server",
            label="Account ID",
            placeholder="Your Cloudflare Account ID",
            required=True,
        ),
        SchemaField(
            name="password",
            label="API Token",
            field_type=FieldType.PASSWORD,
            required=True,
            placeholder="cloudflare api token",
            description="Cloudflare API Token with D1 permissions",
        ),
        SchemaField(
            name="database",
            label="Database Name",
            placeholder="Your D1 database name",
            required=True,
        ),
    ),
    supports_ssh=False,
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
            placeholder="database password",
        ),
    ),
    supports_ssh=False,
)


def get_connection_schema(db_type: str) -> ConnectionSchema:
    from .providers import get_connection_schema as _get_connection_schema

    return _get_connection_schema(db_type)


def get_all_schemas() -> dict[str, ConnectionSchema]:
    """Get all registered connection schemas."""
    from .providers import get_all_schemas as _get_all_schemas

    return _get_all_schemas()


def get_supported_db_types() -> list[str]:
    """Get list of supported database type identifiers."""
    from .providers import get_supported_db_types as _get_supported_db_types

    return _get_supported_db_types()


def is_file_based(db_type: str) -> bool:
    """Check if a database type is file-based (e.g., SQLite, DuckDB).

    Args:
        db_type: Database type identifier

    Returns:
        True if the database is file-based, False otherwise
    """
    from .providers import is_file_based as _is_file_based

    return _is_file_based(db_type)


def has_advanced_auth(db_type: str) -> bool:
    """Check if a database type supports advanced authentication (e.g., SQL Server).

    Args:
        db_type: Database type identifier

    Returns:
        True if the database has advanced auth options, False otherwise
    """
    from .providers import has_advanced_auth as _has_advanced_auth

    return _has_advanced_auth(db_type)


def supports_ssh(db_type: str) -> bool:
    """Check if a database type supports SSH tunneling.

    Args:
        db_type: Database type identifier

    Returns:
        True if the database supports SSH tunneling, False otherwise
    """
    from .providers import supports_ssh as _supports_ssh

    return _supports_ssh(db_type)


def get_default_port(db_type: str) -> str:
    """Get the default port for a database type.

    Args:
        db_type: Database type identifier

    Returns:
        Default port string, or "1433" as fallback for unknown types
    """
    from .providers import get_default_port as _get_default_port

    return _get_default_port(db_type)


def get_display_name(db_type: str) -> str:
    """Get the human-readable display name for a database type.

    Args:
        db_type: Database type identifier

    Returns:
        Display name string, or the db_type itself as fallback
    """
    from .providers import get_display_name as _get_display_name

    return _get_display_name(db_type)
