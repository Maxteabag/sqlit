"""Connection schema for PostgreSQL."""

from sqlit.domains.connections.providers.schema_helpers import (
    SSH_FIELDS,
    TLS_FIELDS,
    ConnectionSchema,
    _database_field,
    _password_field,
    _port_field,
    _server_field,
    _username_field,
)

SCHEMA = ConnectionSchema(
    db_type="postgresql",
    display_name="PostgreSQL",
    fields=(
        _server_field(),
        _port_field("5432"),
        _database_field(),
        _username_field(),
        _password_field(),
    )
    + SSH_FIELDS
    + TLS_FIELDS,
    default_port="5432",
)
