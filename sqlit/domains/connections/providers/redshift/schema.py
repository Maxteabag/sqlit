"""Connection schema for Amazon Redshift."""

from sqlit.domains.connections.providers.schema_helpers import (
    TLS_FIELDS,
    ConnectionSchema,
    FieldType,
    SchemaField,
    SelectOption,
    _get_aws_region_options,
    _get_str_option,
)


def _get_redshift_auth_options() -> tuple[SelectOption, ...]:
    return (
        SelectOption("password", "Password"),
        SelectOption("iam", "IAM"),
    )


def _redshift_auth_is_password(config: dict[str, str]) -> bool:
    return _get_str_option(config, "redshift_auth_method", "password") == "password"


def _redshift_auth_is_iam(config: dict[str, str]) -> bool:
    return _get_str_option(config, "redshift_auth_method") == "iam"


SCHEMA = ConnectionSchema(
    db_type="redshift",
    display_name="Amazon Redshift",
    default_port="5439",
    fields=(
        SchemaField(
            name="server",
            label="Cluster Endpoint",
            placeholder="my-cluster.abc123.us-east-1.redshift.amazonaws.com",
            required=True,
            description="Redshift cluster endpoint",
        ),
        SchemaField(
            name="redshift_auth_method",
            label="Authentication",
            field_type=FieldType.DROPDOWN,
            options=_get_redshift_auth_options(),
            default="password",
        ),
        SchemaField(
            name="username",
            label="Username",
            placeholder="admin",
            required=True,
            group="credentials",
        ),
        SchemaField(
            name="password",
            label="Password",
            field_type=FieldType.PASSWORD,
            required=True,
            group="credentials",
            visible_when=_redshift_auth_is_password,
        ),
        SchemaField(
            name="redshift_cluster_id",
            label="Cluster ID",
            placeholder="my-cluster",
            required=True,
            visible_when=_redshift_auth_is_iam,
            description="Cluster identifier for IAM auth",
        ),
        SchemaField(
            name="redshift_region",
            label="Region",
            field_type=FieldType.DROPDOWN,
            options=_get_aws_region_options(),
            default="us-east-1",
            visible_when=_redshift_auth_is_iam,
        ),
        SchemaField(
            name="redshift_profile",
            label="AWS Profile",
            placeholder="default",
            required=False,
            visible_when=_redshift_auth_is_iam,
            description="AWS CLI profile name",
        ),
        SchemaField(
            name="database",
            label="Database",
            placeholder="dev",
            default="dev",
            required=False,
            group="database_port",
        ),
        SchemaField(
            name="port",
            label="Port",
            placeholder="5439",
            default="5439",
            group="database_port",
        ),
    )
    + TLS_FIELDS,
    supports_ssh=False,
    has_advanced_auth=True,
)
