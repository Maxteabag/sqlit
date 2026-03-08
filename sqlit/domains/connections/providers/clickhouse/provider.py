"""Provider registration."""

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.clickhouse.schema import SCHEMA
from sqlit.domains.connections.providers.docker import DockerDetector
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.clickhouse.adapter import ClickHouseAdapter

    return build_adapter_provider(spec, SCHEMA, ClickHouseAdapter())

SPEC = ProviderSpec(
    db_type="clickhouse",
    display_name="ClickHouse",
    schema_path=("sqlit.domains.connections.providers.clickhouse.schema", "SCHEMA"),
    supports_ssh=True,
    is_file_based=False,
    has_advanced_auth=False,
    default_port="8123",
    requires_auth=False,
    badge_label="ClickHouse",
    provider_factory=_provider_factory,
    docker_detector=DockerDetector(
        image_patterns=("clickhouse",),
        env_vars={
            "user": ("CLICKHOUSE_USER",),
            "password": ("CLICKHOUSE_PASSWORD",),
            "database": ("CLICKHOUSE_DB",),
        },
        default_user="default",
    ),
)

register_provider(SPEC)
