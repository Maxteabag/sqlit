"""Connection schema for AWS Athena."""

from sqlit.domains.connections.providers.schema_helpers import (
    ConnectionSchema,
    FieldType,
    SchemaField,
    SelectOption,
    _get_aws_region_options,
    _get_str_option,
)


def _get_athena_auth_options() -> tuple[SelectOption, ...]:
    return (
        SelectOption("profile", "AWS Profile"),
        SelectOption("keys", "Access Keys"),
    )


def _athena_auth_is_profile(config: dict[str, str]) -> bool:
    return _get_str_option(config, "athena_auth_method", "profile") == "profile"


def _athena_auth_is_keys(config: dict[str, str]) -> bool:
    return _get_str_option(config, "athena_auth_method") == "keys"


SCHEMA = ConnectionSchema(
    db_type="athena",
    display_name="AWS Athena",
    fields=(
        SchemaField(
            name="athena_region_name",
            label="Region",
            field_type=FieldType.DROPDOWN,
            options=_get_aws_region_options(),
            required=True,
            default="us-east-1",
        ),
        SchemaField(
            name="athena_auth_method",
            label="Authentication",
            field_type=FieldType.DROPDOWN,
            options=_get_athena_auth_options(),
            default="profile",
        ),
        SchemaField(
            name="athena_profile_name",
            label="Profile Name",
            placeholder="default",
            required=True,
            default="default",
            description="AWS CLI profile name",
            visible_when=_athena_auth_is_profile,
        ),
        SchemaField(
            name="username",
            label="Access Key",
            placeholder="AWS Access Key ID",
            required=True,
            group="credentials",
            visible_when=_athena_auth_is_keys,
        ),
        SchemaField(
            name="password",
            label="Secret Key",
            field_type=FieldType.PASSWORD,
            placeholder="AWS Secret Access Key",
            required=True,
            group="credentials",
            visible_when=_athena_auth_is_keys,
        ),
        SchemaField(
            name="athena_work_group",
            label="WorkGroup",
            required=True,
            default="primary",
            description="Athena WorkGroup",
        ),
        SchemaField(
            name="athena_s3_staging_dir",
            label="S3 Staging Dir",
            placeholder="s3://your-bucket/path/",
            required=True,
            description="S3 location for query results",
        ),
    ),
    supports_ssh=False,
    has_advanced_auth=True,
)
