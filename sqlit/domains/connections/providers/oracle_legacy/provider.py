"""Provider registration."""

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec
from sqlit.domains.connections.providers.oracle_legacy.schema import SCHEMA


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.oracle_legacy.adapter import OracleLegacyAdapter

    return build_adapter_provider(spec, SCHEMA, OracleLegacyAdapter())


SPEC = ProviderSpec(
    db_type="oracle_legacy",
    display_name="Oracle Legacy",
    schema_path=("sqlit.domains.connections.providers.oracle_legacy.schema", "SCHEMA"),
    supports_ssh=True,
    is_file_based=False,
    has_advanced_auth=False,
    default_port="1521",
    requires_auth=True,
    badge_label="Oracle 11g",
    url_schemes=("oracle11g", "oracle-legacy"),
    provider_factory=_provider_factory,
)

register_provider(SPEC)
