"""Connection schema for MotherDuck."""

from sqlit.domains.connections.providers.schema_helpers import (
    ConnectionSchema,
    FieldType,
    SchemaField,
)

SCHEMA = ConnectionSchema(
    db_type="motherduck",
    display_name="MotherDuck",
    fields=(
        SchemaField(
            name="database",
            label="Database",
            placeholder="(empty = browse all)",
            required=False,
        ),
        SchemaField(
            name="password",
            label="Access Token",
            field_type=FieldType.PASSWORD,
            required=True,
        ),
    ),
    supports_ssh=False,
    is_file_based=False,
    requires_auth=True,
)
