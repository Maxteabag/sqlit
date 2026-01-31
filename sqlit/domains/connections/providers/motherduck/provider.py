"""Provider registration for MotherDuck."""

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec
from sqlit.domains.connections.providers.motherduck.schema import SCHEMA


def _display_info(config) -> str:
    """Display info for MotherDuck connections."""
    database = config.get_option("database", "") or config.database or ""
    if database:
        return f"md:{database}"
    return "md: (default)"


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.motherduck.adapter import MotherDuckAdapter

    return build_adapter_provider(spec, SCHEMA, MotherDuckAdapter())


SPEC = ProviderSpec(
    db_type="motherduck",
    display_name="MotherDuck",
    schema_path=("sqlit.domains.connections.providers.motherduck.schema", "SCHEMA"),
    supports_ssh=False,
    is_file_based=True,  # Use file-based URL parsing (motherduck:///database)
    has_advanced_auth=False,
    default_port="",
    requires_auth=True,
    badge_label="MotherDuck",
    url_schemes=("motherduck", "md"),
    provider_factory=_provider_factory,
    display_info=_display_info,
)

register_provider(SPEC)
