"""Connection schema for CockroachDB."""

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
    db_type="cockroachdb",
    display_name="CockroachDB",
    fields=(
        _server_field(),
        _port_field("26257"),
        _database_field(),
        _username_field(),
        _password_field(),
    )
    + SSH_FIELDS
    + TLS_FIELDS,
    default_port="26257",
    requires_auth=False,
)
