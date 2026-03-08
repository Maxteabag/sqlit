"""Connection schema for MySQL."""

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
    db_type="mysql",
    display_name="MySQL",
    fields=(
        _server_field(),
        _port_field("3306"),
        _database_field(),
        _username_field(),
        _password_field(),
    )
    + SSH_FIELDS
    + TLS_FIELDS,
    default_port="3306",
)
