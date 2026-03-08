"""Connection schema for Cloudflare D1."""

from sqlit.domains.connections.providers.schema_helpers import ConnectionSchema, FieldType, SchemaField

SCHEMA = ConnectionSchema(
    db_type="d1",
    display_name="Cloudflare D1",
    fields=(
        SchemaField(
            name="server",
            label="Account ID",
            placeholder="Your Cloudflare Account ID",
            required=True,
        ),
        SchemaField(
            name="password",
            label="API Token",
            field_type=FieldType.PASSWORD,
            required=True,
            placeholder="cloudflare api token",
            description="Cloudflare API Token with D1 permissions",
        ),
        SchemaField(
            name="database",
            label="Database Name",
            placeholder="Your D1 database name",
            required=True,
        ),
    ),
    supports_ssh=False,
)
