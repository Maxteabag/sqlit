"""Connection schema for IBM Db2."""

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
    db_type="db2",
    display_name="IBM Db2",
    fields=(
        _server_field(),
        _port_field("50000"),
        SchemaField(
            name="database",
            label="Database",
            placeholder="SAMPLE",
            required=True,
        ),
        _username_field(),
        _password_field(),
    )
    + SSH_FIELDS,
    default_port="50000",
)
