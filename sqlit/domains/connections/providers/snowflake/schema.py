"""Connection schema for Snowflake."""

from sqlit.domains.connections.providers.schema_helpers import (
    ConnectionSchema,
    SchemaField,
    _database_field,
    _password_field,
    _username_field,
)

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
        _password_field(),
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
)
