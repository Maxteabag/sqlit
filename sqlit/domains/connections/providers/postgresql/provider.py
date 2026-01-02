"""Provider registration."""

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.docker import DockerDetector
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec
from sqlit.domains.connections.providers.postgresql.schema import SCHEMA


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.postgresql.adapter import PostgreSQLAdapter

    return build_adapter_provider(spec, SCHEMA, PostgreSQLAdapter())

SPEC = ProviderSpec(
    db_type="postgresql",
    display_name="PostgreSQL",
    schema_path=("sqlit.domains.connections.providers.postgresql.schema", "SCHEMA"),
    supports_ssh=True,
    is_file_based=False,
    has_advanced_auth=False,
    default_port="5432",
    requires_auth=True,
    badge_label="PG",
    url_schemes=("postgresql", "postgres"),
    provider_factory=_provider_factory,
    docker_detector=DockerDetector(
        image_patterns=("postgres",),
        env_vars={
            "user": ("POSTGRES_USER",),
            "password": ("POSTGRES_PASSWORD",),
            "database": ("POSTGRES_DB",),
        },
        default_user="postgres",
    ),
)

register_provider(SPEC)
