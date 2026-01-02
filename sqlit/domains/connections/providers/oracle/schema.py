"""Connection schema for Oracle."""

from sqlit.domains.connections.providers.schema_helpers import (
    SSH_FIELDS,
    ConnectionSchema,
    FieldType,
    SchemaField,
    SelectOption,
    _password_field,
    _port_field,
    _username_field,
)


def _get_oracle_role_options() -> tuple[SelectOption, ...]:
    return (
        SelectOption("normal", "Normal"),
        SelectOption("sysdba", "SYSDBA"),
        SelectOption("sysoper", "SYSOPER"),
    )


SCHEMA = ConnectionSchema(
    db_type="oracle",
    display_name="Oracle",
    fields=(
        SchemaField(
            name="server",
            label="Host",
            placeholder="localhost",
            required=True,
            group="server_port",
        ),
        _port_field("1521"),
        SchemaField(
            name="database",
            label="Service Name",
            placeholder="ORCL or XEPDB1",
            required=True,
        ),
        _username_field(),
        _password_field(),
        SchemaField(
            name="oracle_role",
            label="Role",
            field_type=FieldType.DROPDOWN,
            options=_get_oracle_role_options(),
            default="normal",
        ),
    )
    + SSH_FIELDS,
    default_port="1521",
)
