"""Connection schema for Supabase."""

from sqlit.domains.connections.providers.schema_helpers import (
    TLS_FIELDS,
    ConnectionSchema,
    FieldType,
    SchemaField,
    _get_aws_region_options,
)

SCHEMA = ConnectionSchema(
    db_type="supabase",
    display_name="Supabase",
    fields=(
        SchemaField(
            name="supabase_region",
            label="Region",
            field_type=FieldType.DROPDOWN,
            options=_get_aws_region_options(),
            required=True,
            default="us-east-1",
        ),
        SchemaField(
            name="supabase_project_id",
            label="Project ID",
            placeholder="abcdefghijklmnop",
            required=True,
        ),
        SchemaField(
            name="supabase_aws_shard",
            label="AWS Shard",
            placeholder="aws-0",
            default="aws-0",
            description="Pooler shard prefix (e.g. aws-0, aws-1)",
        ),
        SchemaField(
            name="password",
            label="Password",
            field_type=FieldType.PASSWORD,
            required=True,
            placeholder="database password",
        ),
    )
    + TLS_FIELDS,
    supports_ssh=False,
)
