"""Provider registration."""

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.docker import DockerDetector
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec
from sqlit.domains.connections.providers.mssql.schema import SCHEMA


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter

    return build_adapter_provider(spec, SCHEMA, SQLServerAdapter())

SPEC = ProviderSpec(
    db_type="mssql",
    display_name="SQL Server",
    schema_path=("sqlit.domains.connections.providers.mssql.schema", "SCHEMA"),
    supports_ssh=True,
    is_file_based=False,
    has_advanced_auth=True,
    default_port="1433",
    requires_auth=True,
    badge_label="MSSQL",
    url_schemes=("mssql", "sqlserver"),
    provider_factory=_provider_factory,
    docker_detector=DockerDetector(
        image_patterns=("mcr.microsoft.com/mssql",),
        env_vars={
            "user": (),
            "password": ("SA_PASSWORD", "MSSQL_SA_PASSWORD"),
            "database": (),
        },
        default_user="sa",
    ),
)

register_provider(SPEC)
