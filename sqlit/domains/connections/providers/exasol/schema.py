"""Connection schema for Exasol."""

from sqlit.domains.connections.providers.schema_helpers import (
    SSH_FIELDS,
    TLS_FIELDS,
    ConnectionSchema,
    FieldType,
    SchemaField,
    SelectOption,
    _port_field,
    _server_field,
)


def _get_exasol_auth_options() -> tuple[SelectOption, ...]:
    return (
        SelectOption("password", "Username & Password"),
        SelectOption("access_token", "OpenID Access Token"),
        SelectOption("refresh_token", "OpenID Refresh Token"),
    )


def _auth_is_password(v: dict) -> bool:
    return str(v.get("authenticator", "password")) == "password"


def _auth_is_access_token(v: dict) -> bool:
    return str(v.get("authenticator", "password")) == "access_token"


def _auth_is_refresh_token(v: dict) -> bool:
    return str(v.get("authenticator", "password")) == "refresh_token"


SCHEMA = ConnectionSchema(
    db_type="exasol",
    display_name="Exasol",
    fields=(
        _server_field(),
        _port_field("8563"),
        SchemaField(
            name="authenticator",
            label="Authentication",
            field_type=FieldType.DROPDOWN,
            options=_get_exasol_auth_options(),
            default="password",
        ),
        SchemaField(
            name="username",
            label="Username",
            placeholder="sys",
            required=True,
            group="credentials",
            visible_when=_auth_is_password,
        ),
        SchemaField(
            name="password",
            label="Password",
            field_type=FieldType.PASSWORD,
            placeholder="(empty = ask every connect)",
            required=False,
            group="credentials",
            visible_when=_auth_is_password,
        ),
        SchemaField(
            name="access_token",
            label="Access Token",
            field_type=FieldType.PASSWORD,
            placeholder="OpenID access token",
            required=False,
            visible_when=_auth_is_access_token,
        ),
        SchemaField(
            name="refresh_token",
            label="Refresh Token",
            field_type=FieldType.PASSWORD,
            placeholder="OpenID refresh token",
            required=False,
            visible_when=_auth_is_refresh_token,
        ),
        SchemaField(
            name="schema",
            label="Schema",
            placeholder="(empty = browse all)",
            required=False,
            description="Initial Schema",
        ),
    )
    + SSH_FIELDS
    + TLS_FIELDS,
    has_advanced_auth=True,
    default_port="8563",
)
