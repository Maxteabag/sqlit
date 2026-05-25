"""Connection schema for Databricks SQL."""

from sqlit.domains.connections.providers.schema_helpers import (
    ConnectionSchema,
    FieldType,
    SchemaField,
    SelectOption,
)


def _get_databricks_auth_options() -> tuple[SelectOption, ...]:
    return (
        SelectOption("pat", "Personal Access Token"),
        SelectOption("oauth-u2m", "OAuth (Browser)"),
        SelectOption("oauth-m2m", "OAuth (Service Principal)"),
    )


_AUTH_NEEDS_TOKEN = {"pat"}
_AUTH_NEEDS_SP = {"oauth-m2m"}


SCHEMA = ConnectionSchema(
    db_type="databricks",
    display_name="Databricks",
    fields=(
        SchemaField(
            name="server",
            label="Server Hostname",
            placeholder="dbc-a1b2cd34-e5f6.cloud.databricks.com",
            required=True,
            description="Databricks SQL warehouse server hostname (no protocol)",
        ),
        SchemaField(
            name="http_path",
            label="HTTP Path",
            placeholder="/sql/1.0/warehouses/abcdef1234567890",
            required=True,
            description="HTTP path of the SQL warehouse or cluster",
        ),
        SchemaField(
            name="auth_type",
            label="Authentication",
            field_type=FieldType.DROPDOWN,
            options=_get_databricks_auth_options(),
            default="pat",
        ),
        SchemaField(
            name="access_token",
            label="Access Token",
            field_type=FieldType.PASSWORD,
            placeholder="dapi...",
            group="credentials",
            description="Personal Access Token (PAT)",
            visible_when=lambda v: v.get("auth_type", "pat") in _AUTH_NEEDS_TOKEN,
        ),
        SchemaField(
            name="client_id",
            label="Client ID",
            placeholder="service-principal-client-id",
            required=False,
            group="credentials",
            visible_when=lambda v: v.get("auth_type") in _AUTH_NEEDS_SP,
        ),
        SchemaField(
            name="client_secret",
            label="Client Secret",
            field_type=FieldType.PASSWORD,
            placeholder="(secret)",
            required=False,
            group="credentials",
            visible_when=lambda v: v.get("auth_type") in _AUTH_NEEDS_SP,
        ),
        SchemaField(
            name="database",
            label="Catalog",
            placeholder="main",
            required=False,
            description="Unity Catalog name (top-level namespace)",
        ),
        SchemaField(
            name="schema",
            label="Schema",
            placeholder="default",
            required=False,
            description="Default schema within the catalog",
        ),
    ),
    supports_ssh=False,
    has_advanced_auth=True,
)
