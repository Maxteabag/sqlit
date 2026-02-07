"""Connection schema for IBM DB2 for i."""

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
    db_type="db2i",
    display_name="IBM DB2 for i",
    fields=(
        _server_field(),
        _port_field(""),  # Port is optional for IBM i Access ODBC Driver
        SchemaField(
            name="database",
            label="Default Library",
            placeholder="MYLIB",
            required=False,
            description="Default library (schema) to use for queries",
        ),
        _username_field(),
        _password_field(),
        SchemaField(
            name="odbc_driver",
            label="ODBC Driver Name",
            placeholder="IBM i Access ODBC Driver",
            required=False,
            description="Name of the ODBC driver to use (default: IBM i Access ODBC Driver)",
        ),
    )
    + SSH_FIELDS,
    default_port="",
)
