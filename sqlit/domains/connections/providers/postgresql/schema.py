"""Connection schema for PostgreSQL."""

from sqlit.domains.connections.providers.postgresql.auth import (
    POSTGRES_AUTH_AZURE_ENTRA_CLI,
    POSTGRES_AUTH_PASSWORD,
)
from sqlit.domains.connections.providers.schema_helpers import (
    SSH_FIELDS,
    TLS_FIELDS,
    ConnectionSchema,
    FieldType,
    SchemaField,
    SelectOption,
    _database_field,
    _port_field,
    _server_field,
    _username_field,
)


def _auth_is_password(values: dict) -> bool:
    return values.get("postgres_auth_method", POSTGRES_AUTH_PASSWORD) == POSTGRES_AUTH_PASSWORD


SCHEMA = ConnectionSchema(
    db_type="postgresql",
    display_name="PostgreSQL",
    fields=(
        _server_field(required=False),
        _port_field("5432"),
        _database_field(),
        SchemaField(
            name="postgres_auth_method",
            label="Authentication",
            field_type=FieldType.DROPDOWN,
            options=(
                SelectOption(POSTGRES_AUTH_PASSWORD, "Password"),
                SelectOption(
                    POSTGRES_AUTH_AZURE_ENTRA_CLI,
                    "Azure Entra ID (Azure CLI)",
                ),
            ),
            default=POSTGRES_AUTH_PASSWORD,
        ),
        _username_field(required=False),
        SchemaField(
            name="password",
            label="Password",
            field_type=FieldType.PASSWORD,
            placeholder="(empty = ask every connect)",
            group="credentials",
            visible_when=_auth_is_password,
        ),
    )
    + SSH_FIELDS
    + TLS_FIELDS,
    default_port="5432",
)
