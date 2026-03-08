"""Provider registration."""

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.hana.schema import SCHEMA
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.hana.adapter import HanaAdapter

    return build_adapter_provider(spec, SCHEMA, HanaAdapter())


SPEC = ProviderSpec(
    db_type="hana",
    display_name="SAP HANA",
    schema_path=("sqlit.domains.connections.providers.hana.schema", "SCHEMA"),
    supports_ssh=True,
    is_file_based=False,
    has_advanced_auth=False,
    default_port="30015",
    requires_auth=True,
    badge_label="HANA",
    url_schemes=("hana", "saphana"),
    provider_factory=_provider_factory,
)

register_provider(SPEC)
