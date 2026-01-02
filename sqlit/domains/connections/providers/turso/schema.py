"""Connection schema for Turso."""

from sqlit.domains.connections.providers.schema_helpers import ConnectionSchema, FieldType, SchemaField

SCHEMA = ConnectionSchema(
    db_type="turso",
    display_name="Turso",
    fields=(
        SchemaField(
            name="server",
            label="Database URL",
            placeholder="your-db-name.turso.io",
            required=True,
            description="Turso database URL (without libsql:// prefix)",
        ),
        SchemaField(
            name="password",
            label="Auth Token",
            field_type=FieldType.PASSWORD,
            required=False,
            placeholder="auth token (optional)",
            description="Database authentication token, optional for local servers",
        ),
    ),
    supports_ssh=False,
    requires_auth=False,
    default_port="8080",
)
