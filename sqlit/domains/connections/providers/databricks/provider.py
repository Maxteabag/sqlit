"""Provider registration."""

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.databricks.schema import SCHEMA
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.databricks.adapter import DatabricksAdapter

    return build_adapter_provider(spec, SCHEMA, DatabricksAdapter())


SPEC = ProviderSpec(
    db_type="databricks",
    display_name="Databricks",
    schema_path=("sqlit.domains.connections.providers.databricks.schema", "SCHEMA"),
    supports_ssh=False,
    is_file_based=False,
    has_advanced_auth=True,
    default_port="",
    requires_auth=True,
    badge_label="DBRX",
    url_schemes=("databricks",),
    provider_factory=_provider_factory,
)

register_provider(SPEC)
