"""Connection schema for Snowflake."""

from sqlit.domains.connections.providers.schema_helpers import (
    ConnectionSchema,
    FieldType,
    SchemaField,
    SelectOption,
    _database_field,
    _password_field,
    _username_field,
)


def _get_snowflake_auth_options() -> tuple[SelectOption, ...]:
    return (
        SelectOption("default", "Username & Password"),
        SelectOption("externalbrowser", "SSO (Browser)"),
        SelectOption("snowflake_jwt", "Key Pair (JWT)"),
        SelectOption("oauth", "OAuth Token"),
    )


# Auth types that need password
_AUTH_NEEDS_PASSWORD = {"default"}
# Auth types that need private key
_AUTH_NEEDS_PRIVATE_KEY = {"snowflake_jwt"}
# Auth types that need OAuth token
_AUTH_NEEDS_OAUTH = {"oauth"}


SCHEMA = ConnectionSchema(
    db_type="snowflake",
    display_name="Snowflake",
    fields=(
        SchemaField(
            name="server",
            label="Account",
            placeholder="xy12345.us-east-2.aws",
            required=True,
            description="Snowflake Account Identifier",
        ),
        _username_field(),
        SchemaField(
            name="authenticator",
            label="Authentication",
            field_type=FieldType.DROPDOWN,
            options=_get_snowflake_auth_options(),
            default="default",
        ),
        SchemaField(
            name="password",
            label="Password",
            field_type=FieldType.PASSWORD,
            placeholder="(empty = ask every connect)",
            group="credentials",
            visible_when=lambda v: v.get("authenticator", "default") in _AUTH_NEEDS_PASSWORD,
        ),
        SchemaField(
            name="private_key_file",
            label="Private Key File",
            field_type=FieldType.FILE,
            placeholder="/path/to/rsa_key.p8",
            required=False,
            description="Path to private key file for JWT authentication",
            visible_when=lambda v: v.get("authenticator") in _AUTH_NEEDS_PRIVATE_KEY,
        ),
        SchemaField(
            name="private_key_file_pwd",
            label="Private Key Password",
            field_type=FieldType.PASSWORD,
            placeholder="(optional)",
            required=False,
            description="Password for encrypted private key",
            visible_when=lambda v: v.get("authenticator") in _AUTH_NEEDS_PRIVATE_KEY,
        ),
        SchemaField(
            name="oauth_token",
            label="OAuth Token",
            field_type=FieldType.PASSWORD,
            placeholder="OAuth access token",
            required=False,
            visible_when=lambda v: v.get("authenticator") in _AUTH_NEEDS_OAUTH,
        ),
        _database_field(),
        SchemaField(
            name="warehouse",
            label="Warehouse",
            placeholder="COMPUTE_WH",
            required=False,
            description="Virtual Warehouse to use",
        ),
        SchemaField(
            name="schema",
            label="Schema",
            placeholder="PUBLIC",
            required=False,
            description="Initial Schema",
        ),
        SchemaField(
            name="role",
            label="Role",
            placeholder="ACCOUNTADMIN",
            required=False,
            description="User Role",
        ),
    ),
    supports_ssh=False,
    has_advanced_auth=True,
)
