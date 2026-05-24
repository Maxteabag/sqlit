"""Connection schema for SurrealDB."""

from sqlit.domains.connections.providers.schema_helpers import (
    SSH_FIELDS,
    ConnectionSchema,
    FieldType,
    SchemaField,
    SelectOption,
    _password_field,
    _port_field,
    _server_field,
    _username_field,
)

SCHEMA = ConnectionSchema(
    db_type="surrealdb",
    display_name="SurrealDB",
    fields=(
        _server_field(),
        _port_field("8000"),
        SchemaField(
            name="namespace",
            label="Namespace",
            placeholder="test",
            required=True,
        ),
        SchemaField(
            name="database",
            label="Database",
            placeholder="test",
            required=True,
        ),
        _username_field(),
        _password_field(),
        SchemaField(
            name="use_ssl",
            label="Use SSL",
            field_type=FieldType.SELECT,
            options=(
                SelectOption("false", "No"),
                SelectOption("true", "Yes"),
            ),
            default="false",
            advanced=True,
        ),
    )
    + SSH_FIELDS,
    default_port="8000",
    requires_auth=True,
)
