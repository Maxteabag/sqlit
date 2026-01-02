"""Connection schema for Apache Arrow Flight SQL."""

from sqlit.domains.connections.providers.schema_helpers import (
    SSH_FIELDS,
    ConnectionSchema,
    FieldType,
    SchemaField,
    SelectOption,
    _database_field,
    _port_field,
    _server_field,
)


def _flight_auth_is_basic(v: dict) -> bool:
    return v.get("flight_auth_type") == "basic"


def _flight_auth_is_token(v: dict) -> bool:
    return v.get("flight_auth_type") == "token"


def _get_flight_auth_options() -> tuple[SelectOption, ...]:
    return (
        SelectOption("basic", "Basic Auth (Username/Password)"),
        SelectOption("token", "Bearer Token"),
        SelectOption("none", "No Authentication"),
    )


def _get_flight_tls_options() -> tuple[SelectOption, ...]:
    return (
        SelectOption("auto", "Auto (detect from port)"),
        SelectOption("enabled", "Enabled"),
        SelectOption("disabled", "Disabled"),
    )


SCHEMA = ConnectionSchema(
    db_type="flight",
    display_name="Arrow Flight SQL",
    fields=(
        _server_field(),
        _port_field("8815"),
        SchemaField(
            name="flight_auth_type",
            label="Authentication",
            field_type=FieldType.DROPDOWN,
            options=_get_flight_auth_options(),
            default="basic",
        ),
        SchemaField(
            name="username",
            label="Username",
            placeholder="username",
            required=True,
            group="credentials",
            visible_when=_flight_auth_is_basic,
        ),
        SchemaField(
            name="password",
            label="Password",
            field_type=FieldType.PASSWORD,
            placeholder="(empty = ask every connect)",
            group="credentials",
            visible_when=_flight_auth_is_basic,
        ),
        SchemaField(
            name="flight_token",
            label="Bearer Token",
            field_type=FieldType.PASSWORD,
            placeholder="JWT or API token",
            required=True,
            visible_when=_flight_auth_is_token,
        ),
        SchemaField(
            name="flight_use_tls",
            label="Use TLS",
            field_type=FieldType.DROPDOWN,
            options=_get_flight_tls_options(),
            default="auto",
            advanced=True,
        ),
        _database_field(placeholder="(optional catalog name)"),
    )
    + SSH_FIELDS,
    default_port="8815",
    requires_auth=False,  # Some Flight SQL servers allow anonymous access
    has_advanced_auth=True,
)
