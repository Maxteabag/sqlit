"""Connection schema for Teradata."""

from sqlit.domains.connections.providers.schema_helpers import (
    SSH_FIELDS,
    ConnectionSchema,
    SchemaField,
    _password_field,
    _port_field,
    _server_field,
    _username_field,
)

SCHEMA = ConnectionSchema(
    db_type="teradata",
    display_name="Teradata",
    fields=(
        _server_field(),
        _port_field("1025"),
        SchemaField(
            name="database",
            label="Database",
            placeholder="(optional)",
            required=False,
        ),
        _username_field(),
        _password_field(),
    )
    + SSH_FIELDS,
    default_port="1025",
)
