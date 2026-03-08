"""Provider registration."""

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec
from sqlit.domains.connections.providers.teradata.schema import SCHEMA


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.teradata.adapter import TeradataAdapter

    return build_adapter_provider(spec, SCHEMA, TeradataAdapter())


SPEC = ProviderSpec(
    db_type="teradata",
    display_name="Teradata",
    schema_path=("sqlit.domains.connections.providers.teradata.schema", "SCHEMA"),
    supports_ssh=True,
    is_file_based=False,
    has_advanced_auth=False,
    default_port="1025",
    requires_auth=True,
    badge_label="Teradata",
    url_schemes=("teradata",),
    provider_factory=_provider_factory,
)

register_provider(SPEC)
