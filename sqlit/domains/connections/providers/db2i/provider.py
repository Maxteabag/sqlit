"""Provider registration for IBM DB2 for i."""

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.db2i.schema import SCHEMA
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.db2i.adapter import Db2iAdapter

    return build_adapter_provider(spec, SCHEMA, Db2iAdapter())


SPEC = ProviderSpec(
    db_type="db2i",
    display_name="IBM DB2 for i",
    schema_path=("sqlit.domains.connections.providers.db2i.schema", "SCHEMA"),
    supports_ssh=True,
    is_file_based=False,
    has_advanced_auth=False,
    default_port="",
    requires_auth=True,
    badge_label="DB2i",
    url_schemes=("db2i",),
    provider_factory=_provider_factory,
)

register_provider(SPEC)
