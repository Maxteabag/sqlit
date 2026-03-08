"""Provider registration."""

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec
from sqlit.domains.connections.providers.supabase.schema import SCHEMA


def _supabase_display_info(config: object) -> str:
    region = getattr(config, "get_option", lambda name, default="": default)("supabase_region", "")
    if region:
        name = getattr(config, "name", "Supabase")
        return f"{name} ({region})"
    return getattr(config, "name", "Supabase")


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.supabase.adapter import SupabaseAdapter

    return build_adapter_provider(spec, SCHEMA, SupabaseAdapter())


SPEC = ProviderSpec(
    db_type="supabase",
    display_name="Supabase",
    schema_path=("sqlit.domains.connections.providers.supabase.schema", "SCHEMA"),
    supports_ssh=False,
    is_file_based=False,
    has_advanced_auth=False,
    default_port="",
    requires_auth=True,
    badge_label="Supabase",
    display_info=_supabase_display_info,
    provider_factory=_provider_factory,
)

register_provider(SPEC)
