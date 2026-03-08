"""Provider registration."""

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.docker import DockerDetector
from sqlit.domains.connections.providers.firebird.schema import SCHEMA
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.firebird.adapter import FirebirdAdapter

    return build_adapter_provider(spec, SCHEMA, FirebirdAdapter())

SPEC = ProviderSpec(
    db_type="firebird",
    display_name="Firebird",
    schema_path=("sqlit.domains.connections.providers.firebird.schema", "SCHEMA"),
    supports_ssh=True,
    is_file_based=False,
    has_advanced_auth=False,
    default_port="3050",
    requires_auth=True,
    badge_label="FB",
    url_schemes=("firebird",),
    provider_factory=_provider_factory,
    docker_detector=DockerDetector(
        image_patterns=("firebirdsql/firebird",),
        env_vars={
            "user": ("FIREBIRD_USER",),
            "password": ("FIREBIRD_PASSWORD",),
            "database": ("FIREBIRD_DATABASE",),
        },
        default_user="SYSDBA",
    ),
)

register_provider(SPEC)
