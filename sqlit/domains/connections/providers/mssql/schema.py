"""Connection schema for SQL Server."""

from sqlit.domains.connections.providers.schema_helpers import (
    SSH_FIELDS,
    TLS_MODE_FIELD,
    ConnectionSchema,
    FieldType,
    SchemaField,
    SelectOption,
    _database_field,
    _port_field,
)


def _get_mssql_auth_options() -> tuple[SelectOption, ...]:
    return (
        SelectOption("sql", "SQL Server Authentication"),
        SelectOption("windows", "Windows Authentication"),
        SelectOption("ad_password", "Azure AD Password"),
        SelectOption("ad_interactive", "Azure AD Interactive"),
        SelectOption("ad_integrated", "Azure AD Integrated"),
        SelectOption("ad_default", "Azure AD Default (CLI)"),
    )


# Auth types that need username
_MSSQL_AUTH_NEEDS_USERNAME = {"sql", "ad_password", "ad_interactive"}
# Auth types that need password
_MSSQL_AUTH_NEEDS_PASSWORD = {"sql", "ad_password"}


SCHEMA = ConnectionSchema(
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
        TLS_MODE_FIELD,
        SchemaField(
            name="tls_trust_server_certificate",
            label="Trust Server Certificate",
            field_type=FieldType.SELECT,
            options=(
                SelectOption("yes", "Yes"),
                SelectOption("no", "No"),
            ),
            default="yes",
            visible_when=lambda v: str(v.get("tls_mode", "default")).lower() not in {"", "default", "disable"},
            tab="tls",
        ),
    )
    + SSH_FIELDS,
    has_advanced_auth=True,
    default_port="1433",
)
