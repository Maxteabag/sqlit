"""Provider registration."""

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.duckdb.schema import SCHEMA
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.duckdb.adapter import DuckDBAdapter

    return build_adapter_provider(spec, SCHEMA, DuckDBAdapter())

SPEC = ProviderSpec(
    db_type="duckdb",
    display_name="DuckDB",
    schema_path=("sqlit.domains.connections.providers.duckdb.schema", "SCHEMA"),
    supports_ssh=False,
    is_file_based=True,
    has_advanced_auth=False,
    default_port="",
    requires_auth=True,
    badge_label="DuckDB",
    url_schemes=("duckdb",),
    provider_factory=_provider_factory,
)

register_provider(SPEC)
