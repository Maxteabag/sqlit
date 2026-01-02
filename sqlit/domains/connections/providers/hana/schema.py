"""Connection schema for SAP HANA."""

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
    db_type="hana",
    display_name="SAP HANA",
    fields=(
        _server_field(),
        _port_field("30015"),
        SchemaField(
            name="database",
            label="Tenant Database",
            placeholder="(optional)",
            required=False,
        ),
        _username_field(),
        _password_field(),
        SchemaField(
            name="schema",
            label="Schema",
            placeholder="PUBLIC",
            required=False,
        ),
    )
    + SSH_FIELDS,
    default_port="30015",
)
