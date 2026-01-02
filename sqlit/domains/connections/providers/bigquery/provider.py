"""Provider registration."""

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.bigquery.schema import SCHEMA
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.bigquery.adapter import BigQueryAdapter

    return build_adapter_provider(spec, SCHEMA, BigQueryAdapter())

SPEC = ProviderSpec(
    db_type="bigquery",
    display_name="Google BigQuery",
    schema_path=("sqlit.domains.connections.providers.bigquery.schema", "SCHEMA"),
    supports_ssh=False,
    is_file_based=False,
    has_advanced_auth=True,
    default_port="",
    requires_auth=False,
    badge_label="BQ",
    url_schemes=("bigquery",),
    provider_factory=_provider_factory,
)

register_provider(SPEC)
