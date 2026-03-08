"""Provider registration for Google Cloud Spanner."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlit.domains.connections.providers.adapter_provider import build_adapter_provider
from sqlit.domains.connections.providers.catalog import register_provider
from sqlit.domains.connections.providers.model import DatabaseProvider, ProviderSpec
from sqlit.domains.connections.providers.spanner.schema import SCHEMA

if TYPE_CHECKING:
    pass


def _provider_factory(spec: ProviderSpec) -> DatabaseProvider:
    from sqlit.domains.connections.providers.spanner.adapter import SpannerAdapter

    return build_adapter_provider(spec, SCHEMA, SpannerAdapter())


SPEC = ProviderSpec(
    db_type="spanner",
    display_name="Google Cloud Spanner",
    schema_path=("sqlit.domains.connections.providers.spanner.schema", "SCHEMA"),
    supports_ssh=False,
    is_file_based=False,
    has_advanced_auth=True,
    default_port="",
    requires_auth=False,
    badge_label="Spanner",
    url_schemes=("spanner",),
    provider_factory=_provider_factory,
)

register_provider(SPEC)
