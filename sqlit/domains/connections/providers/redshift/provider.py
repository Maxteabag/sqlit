"""Provider registration."""

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec
from sqlit.domains.connections.providers.redshift.schema import SCHEMA


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.redshift.adapter import RedshiftAdapter

    return build_adapter_provider(spec, SCHEMA, RedshiftAdapter())

SPEC = ProviderSpec(
    db_type="redshift",
    display_name="Amazon Redshift",
    schema_path=("sqlit.domains.connections.providers.redshift.schema", "SCHEMA"),
    supports_ssh=False,
    is_file_based=False,
    has_advanced_auth=True,
    default_port="5439",
    requires_auth=True,
    badge_label="RS",
    url_schemes=("redshift",),
    provider_factory=_provider_factory,
)

register_provider(SPEC)
