"""Connection schema for Impala."""

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


def _get_auth_mechanism_options() -> tuple[SelectOption, ...]:
    return (
        SelectOption("NOSASL", "No Auth"),
        SelectOption("PLAIN", "PLAIN (LDAP)"),
        SelectOption("GSSAPI", "Kerberos (GSSAPI)"),
    )


SCHEMA = ConnectionSchema(
    db_type="impala",
    display_name="Impala",
    fields=(
        _server_field(),
        _port_field("21050"),
        SchemaField(
            name="database",
            label="Database",
            placeholder="default",
            required=False,
        ),
        _username_field(required=False),
        _password_field(),
        SchemaField(
            name="auth_mechanism",
            label="Auth Mechanism",
            field_type=FieldType.SELECT,
            options=_get_auth_mechanism_options(),
            default="NOSASL",
            advanced=True,
        ),
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
    default_port="21050",
    requires_auth=False,
)
