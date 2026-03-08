"""Connection schema for Firebird."""

from sqlit.domains.connections.providers.schema_helpers import (
    SSH_FIELDS,
    ConnectionSchema,
    SchemaField,
    _database_field,
    _password_field,
    _port_field,
    _username_field,
)

SCHEMA = ConnectionSchema(
    db_type="firebird",
    display_name="Firebird",
    fields=(
        SchemaField(
            name="server",
            label="Server",
            placeholder="(local connection)",
            required=False,
            group="server_port",
        ),
        _port_field("3050"),
        _database_field(),
        _username_field(),
        _password_field(),
    )
    + SSH_FIELDS,
    default_port="3050",
)
