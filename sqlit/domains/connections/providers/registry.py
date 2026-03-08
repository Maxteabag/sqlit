"""Deprecated registry shim.

Prefer sqlit.domains.connections.providers.catalog/metadata/validation.
"""

from __future__ import annotations

from typing import Any, cast

from sqlit.domains.connections.providers.adapters.base import DatabaseAdapter
from sqlit.domains.connections.providers.catalog import (
    get_all_schemas,
    get_db_type_for_scheme,
    get_provider,
    get_provider_schema,
    get_provider_spec,
    get_supported_db_types,
    get_supported_url_schemes,
    get_url_scheme_map,
    iter_provider_schemas,
    register_provider,
)
from sqlit.domains.connections.providers.config_service import (
    normalize_connection_config,
    validate_database_required,
)
from sqlit.domains.connections.providers.metadata import (
    get_badge_label,
    get_connection_display_info,
    get_default_port,
    get_display_name,
    has_advanced_auth,
    is_file_based,
    requires_auth,
    supports_ssh,
)


def get_adapter(db_type: str) -> DatabaseAdapter:
    """Return the adapter instance for a provider db_type."""
    provider = get_provider(db_type)
    return cast(DatabaseAdapter, provider.connection_factory)


def get_connection_schema(db_type: str) -> Any:
    """Compatibility alias for provider schemas."""
    return get_provider_schema(db_type)


def requires_database_selection(db_type: str) -> bool:
    """Return True when a database must be specified to query."""
    try:
        provider = get_provider(db_type)
    except Exception:
        return False
    return not provider.capabilities.supports_cross_database_queries


__all__ = [
    "get_adapter",
    "get_all_schemas",
    "get_badge_label",
    "get_connection_display_info",
    "get_connection_schema",
    "get_db_type_for_scheme",
    "get_default_port",
    "get_display_name",
    "get_provider",
    "get_provider_schema",
    "get_provider_spec",
    "get_supported_db_types",
    "get_supported_url_schemes",
    "get_url_scheme_map",
    "has_advanced_auth",
    "is_file_based",
    "iter_provider_schemas",
    "normalize_connection_config",
    "register_provider",
    "requires_auth",
    "requires_database_selection",
    "supports_ssh",
    "validate_database_required",
]
