"""Connection schema for ClickHouse."""

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
    db_type="clickhouse",
    display_name="ClickHouse",
    fields=(
        _server_field(),
        _port_field("8123"),
        _database_field(placeholder="default"),
        _username_field(required=False),
        _password_field(),
    )
    + SSH_FIELDS
    + TLS_FIELDS,
    default_port="8123",
    requires_auth=False,
)
