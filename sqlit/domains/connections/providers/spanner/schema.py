"""Connection schema for Google Cloud Spanner."""

from __future__ import annotations

from sqlit.domains.connections.providers.schema_helpers import (
    ConnectionSchema,
    FieldType,
    SchemaField,
    SelectOption,
    _get_str_option,
)


def _get_spanner_auth_options() -> tuple[SelectOption, ...]:
    return (
        SelectOption("default", "Application Default"),
        SelectOption("service_account", "Service Account"),
    )


def _spanner_auth_is_service_account(config: dict[str, str]) -> bool:
    return _get_str_option(config, "spanner_auth_method") == "service_account"


SCHEMA = ConnectionSchema(
    db_type="spanner",
    display_name="Google Cloud Spanner",
    fields=(
        SchemaField(
            name="spanner_project",
            label="Project ID",
            placeholder="my-gcp-project",
            required=True,
            description="GCP Project ID",
        ),
        SchemaField(
            name="spanner_instance",
            label="Instance ID",
            placeholder="my-instance",
            required=True,
            description="Spanner instance ID",
        ),
        SchemaField(
            name="database",
            label="Database ID",
            placeholder="my-database",
            required=True,
            description="Spanner database ID",
        ),
        SchemaField(
            name="spanner_auth_method",
            label="Authentication",
            field_type=FieldType.DROPDOWN,
            options=_get_spanner_auth_options(),
            default="default",
        ),
        SchemaField(
            name="spanner_credentials_path",
            label="Service Account Key",
            placeholder="/path/to/service-account.json",
            required=True,
            visible_when=_spanner_auth_is_service_account,
            description="Path to service account JSON key file",
        ),
        SchemaField(
            name="spanner_database_role",
            label="Database Role",
            placeholder="(optional)",
            required=False,
            description="Fine-grained access control role (optional)",
        ),
        SchemaField(
            name="spanner_emulator_host",
            label="Emulator Host",
            placeholder="localhost:9010",
            required=False,
            description="Spanner emulator host:port (leave empty for real Spanner)",
        ),
    ),
    supports_ssh=False,
    has_advanced_auth=True,
    requires_auth=False,
)
