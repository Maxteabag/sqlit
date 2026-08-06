"""Connection schema for Trino."""

from sqlit.domains.connections.providers.schema_helpers import (
    SSH_FIELDS,
    ConnectionSchema,
    FieldType,
    SchemaField,
    SelectOption,
    _port_field,
    _server_field,
    _username_field,
)


def _get_http_scheme_options() -> tuple[SelectOption, ...]:
    return (
        SelectOption("http", "HTTP"),
        SelectOption("https", "HTTPS"),
    )


def _get_authentication_options() -> tuple[SelectOption, ...]:
    return (
        SelectOption("none", "None"),
        SelectOption("basic", "Basic"),
        SelectOption("kerberos", "Kerberos"),
        SelectOption("gssapi", "GSSAPI"),
    )


def _get_kerberos_mutual_authentication_options() -> tuple[SelectOption, ...]:
    return (
        SelectOption("driver", "Driver default"),
        SelectOption("required", "Required"),
        SelectOption("optional", "Optional"),
        SelectOption("disabled", "Disabled"),
    )


def _trino_auth_is_basic(config: dict[str, str]) -> bool:
    return config.get("trino_auth_method", "basic") == "basic"


def _trino_auth_is_kerberos(config: dict[str, str]) -> bool:
    return config.get("trino_auth_method", "basic") in {"kerberos", "gssapi"}


SCHEMA = ConnectionSchema(
    db_type="trino",
    display_name="Trino",
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
        SchemaField(
            name="trino_auth_method",
            label="Authentication",
            field_type=FieldType.SELECT,
            options=_get_authentication_options(),
            default="basic",
        ),
        SchemaField(
            name="password",
            label="Password",
            field_type=FieldType.PASSWORD,
            placeholder="(empty = ask every connect)",
            group="credentials",
            visible_when=_trino_auth_is_basic,
        ),
        SchemaField(
            name="trino_kerberos_service_name",
            label="Kerberos Service Name",
            placeholder="HTTP",
            description="Service principal name; blank uses HTTP for Kerberos",
            visible_when=_trino_auth_is_kerberos,
        ),
        SchemaField(
            name="trino_kerberos_hostname_override",
            label="Kerberos Hostname Override",
            placeholder="trino.example.com",
            description="Hostname used to construct the Kerberos service principal",
            visible_when=_trino_auth_is_kerberos,
        ),
        SchemaField(
            name="trino_kerberos_delegate",
            label="Delegate Kerberos Credentials",
            field_type=FieldType.SELECT,
            options=(SelectOption("false", "No"), SelectOption("true", "Yes")),
            default="false",
            visible_when=_trino_auth_is_kerberos,
            advanced=True,
        ),
        SchemaField(
            name="trino_kerberos_mutual_authentication",
            label="Mutual Authentication",
            field_type=FieldType.SELECT,
            options=_get_kerberos_mutual_authentication_options(),
            default="driver",
            visible_when=_trino_auth_is_kerberos,
            advanced=True,
        ),
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
