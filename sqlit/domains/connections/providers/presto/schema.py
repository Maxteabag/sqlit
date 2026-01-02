"""Connection schema for Presto."""

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


def _get_http_scheme_options() -> tuple[SelectOption, ...]:
    return (
        SelectOption("http", "HTTP"),
        SelectOption("https", "HTTPS"),
    )


SCHEMA = ConnectionSchema(
    db_type="presto",
    display_name="Presto",
    fields=(
        _server_field(),
        _port_field("8080"),
        SchemaField(
            name="database",
            label="Catalog",
            placeholder="hive",
            required=False,
        ),
        SchemaField(
            name="schema",
            label="Schema",
            placeholder="default",
            required=False,
        ),
        _username_field(),
        _password_field(),
        SchemaField(
            name="http_scheme",
            label="HTTP Scheme",
            field_type=FieldType.SELECT,
            options=_get_http_scheme_options(),
            default="http",
            advanced=True,
        ),
    )
    + SSH_FIELDS,
    default_port="8080",
)
