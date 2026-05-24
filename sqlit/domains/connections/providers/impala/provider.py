"""Provider registration for Impala."""

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.impala.schema import SCHEMA
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.impala.adapter import ImpalaAdapter

    return build_adapter_provider(spec, SCHEMA, ImpalaAdapter())


SPEC = ProviderSpec(
    db_type="impala",
    display_name="Impala",
    schema_path=("sqlit.domains.connections.providers.impala.schema", "SCHEMA"),
    supports_ssh=True,
    is_file_based=False,
    has_advanced_auth=True,  # Kerberos support
    default_port="21050",
    requires_auth=False,
    badge_label="Impala",
    url_schemes=("impala",),
    provider_factory=_provider_factory,
)

register_provider(SPEC)
