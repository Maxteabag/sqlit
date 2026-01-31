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


def _get_oracle_connection_type_options() -> tuple[SelectOption, ...]:
    return (
        SelectOption("service_name", "Service Name"),
        SelectOption("sid", "SID"),
    )


def _oracle_connection_type_is_service_name(values: dict) -> bool:
    return values.get("oracle_connection_type", "service_name") != "sid"


def _oracle_connection_type_is_sid(values: dict) -> bool:
    return values.get("oracle_connection_type") == "sid"


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
            name="oracle_connection_type",
            label="Connection Type",
            field_type=FieldType.DROPDOWN,
            options=_get_oracle_connection_type_options(),
            default="service_name",
        ),
        SchemaField(
            name="database",
            label="Service Name",
            placeholder="ORCL or XEPDB1",
            required=True,
            visible_when=_oracle_connection_type_is_service_name,
        ),
        SchemaField(
            name="oracle_sid",
            label="SID",
            placeholder="ORCL",
            required=True,
            visible_when=_oracle_connection_type_is_sid,
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
