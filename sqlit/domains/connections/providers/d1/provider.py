"""Provider registration."""

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.d1.schema import SCHEMA
from sqlit.domains.connections.providers.docker import DockerDetector
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.d1.adapter import D1Adapter

    return build_adapter_provider(spec, SCHEMA, D1Adapter())

SPEC = ProviderSpec(
    db_type="d1",
    display_name="Cloudflare D1",
    schema_path=("sqlit.domains.connections.providers.d1.schema", "SCHEMA"),
    supports_ssh=False,
    is_file_based=False,
    has_advanced_auth=False,
    default_port="",
    requires_auth=True,
    badge_label="D1",
    docker_detector=DockerDetector(
        image_patterns=("miniflare", "sqlit-miniflare"),
        env_vars={
            "user": ("D1_ACCOUNT_ID",),
            "password": ("D1_API_TOKEN",),
            "database": ("D1_DATABASE",),
        },
        default_database="test-d1",
    ),
    provider_factory=_provider_factory,
)

register_provider(SPEC)
