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
            name="file_path",
            label="Database",
            placeholder="my_database",
            required=True,
        ),
        SchemaField(
            name="motherduck_token",
            label="Access Token",
            field_type=FieldType.PASSWORD,
            required=True,
        ),
    ),
    supports_ssh=False,
    is_file_based=True,
    requires_auth=True,
)
