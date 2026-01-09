"""Connection schema for Google BigQuery."""

from sqlit.domains.connections.providers.schema_helpers import (
    ConnectionSchema,
    FieldType,
    SchemaField,
    SelectOption,
    _get_str_option,
)


def _get_bigquery_auth_options() -> tuple[SelectOption, ...]:
    return (
        SelectOption("default", "Application Default"),
        SelectOption("service_account", "Service Account"),
    )


def _bigquery_auth_is_service_account(config: dict[str, str]) -> bool:
    return _get_str_option(config, "bigquery_auth_method") == "service_account"


SCHEMA = ConnectionSchema(
    db_type="bigquery",
    display_name="Google BigQuery",
    fields=(
        SchemaField(
            name="server",
            label="Project ID",
            placeholder="my-gcp-project",
            required=False,
            description="GCP Project ID (or infer from environment)",
        ),
        SchemaField(
            name="port",
            label="Emulator Port",
            placeholder="9050",
            required=False,
            description="Port for local BigQuery emulator (leave empty for real BigQuery)",
        ),
        SchemaField(
            name="database",
            label="Dataset",
            placeholder="my_dataset",
            required=False,
            description="Default dataset (optional)",
        ),
        SchemaField(
            name="bigquery_auth_method",
            label="Authentication",
            field_type=FieldType.DROPDOWN,
            options=_get_bigquery_auth_options(),
            default="default",
        ),
        SchemaField(
            name="bigquery_credentials_path",
            label="Service Account Key",
            placeholder="/path/to/service-account.json",
            required=True,
            visible_when=_bigquery_auth_is_service_account,
            description="Path to service account JSON key file",
        ),
        SchemaField(
            name="bigquery_location",
            label="Location",
            placeholder="US",
            default="US",
            required=False,
            description="Dataset location (US, EU, etc.)",
        ),
    ),
    supports_ssh=False,
    has_advanced_auth=True,
    requires_auth=False,
)
