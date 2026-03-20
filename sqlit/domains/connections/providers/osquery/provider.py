"""Provider registration for osquery."""

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec
from sqlit.domains.connections.providers.osquery.schema import SCHEMA


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.osquery.adapter import OsqueryAdapter

    return build_adapter_provider(spec, SCHEMA, OsqueryAdapter())


SPEC = ProviderSpec(
    db_type="osquery",
    display_name="osquery",
    schema_path=("sqlit.domains.connections.providers.osquery.schema", "SCHEMA"),
    supports_ssh=False,
    is_file_based=False,
    has_advanced_auth=False,
    default_port="",
    requires_auth=False,
    badge_label="osq",
    url_schemes=("osquery",),
    provider_factory=_provider_factory,
)

register_provider(SPEC)
