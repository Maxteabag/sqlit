"""Provider registration."""

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.docker import DockerDetector
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec
from sqlit.domains.connections.providers.turso.schema import SCHEMA


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.turso.adapter import TursoAdapter

    return build_adapter_provider(spec, SCHEMA, TursoAdapter())

SPEC = ProviderSpec(
    db_type="turso",
    display_name="Turso",
    schema_path=("sqlit.domains.connections.providers.turso.schema", "SCHEMA"),
    supports_ssh=False,
    is_file_based=False,
    has_advanced_auth=False,
    default_port="8080",
    requires_auth=False,
    badge_label="Turso",
    url_schemes=("libsql",),
    provider_factory=_provider_factory,
    docker_detector=DockerDetector(
        image_patterns=("ghcr.io/tursodatabase/libsql-server", "tursodatabase/libsql-server"),
        env_vars={
            "user": (),
            "password": (),
            "database": (),
        },
        default_user="",
        default_database="",
    ),
)

register_provider(SPEC)
