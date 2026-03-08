"""Provider registration."""

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec
from sqlit.domains.connections.providers.trino.schema import SCHEMA


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.trino.adapter import TrinoAdapter

    return build_adapter_provider(spec, SCHEMA, TrinoAdapter())


SPEC = ProviderSpec(
    db_type="trino",
    display_name="Trino",
    schema_path=("sqlit.domains.connections.providers.trino.schema", "SCHEMA"),
    supports_ssh=True,
    is_file_based=False,
    has_advanced_auth=False,
    default_port="8080",
    requires_auth=True,
    badge_label="Trino",
    url_schemes=("trino",),
    provider_factory=_provider_factory,
)

register_provider(SPEC)
