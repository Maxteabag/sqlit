"""Provider metadata accessors (UI-friendly labels, display info)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.providers.catalog import get_provider

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


def _get_provider_or_none(db_type: str) -> Any:
    try:
        return get_provider(db_type)
    except Exception:
        return None


def get_display_name(db_type: str) -> str:
    provider = _get_provider_or_none(db_type)
    return provider.metadata.display_name if provider else db_type


def get_badge_label(db_type: str) -> str:
    provider = _get_provider_or_none(db_type)
    return provider.metadata.badge_label if provider else db_type


def get_default_port(db_type: str) -> str:
    provider = _get_provider_or_none(db_type)
    return provider.metadata.default_port if provider else "1433"


def supports_ssh(db_type: str) -> bool:
    provider = _get_provider_or_none(db_type)
    return provider.metadata.supports_ssh if provider else False


def is_file_based(db_type: str) -> bool:
    provider = _get_provider_or_none(db_type)
    return provider.metadata.is_file_based if provider else False


def has_advanced_auth(db_type: str) -> bool:
    provider = _get_provider_or_none(db_type)
    return provider.metadata.has_advanced_auth if provider else False


def requires_auth(db_type: str) -> bool:
    provider = _get_provider_or_none(db_type)
    return provider.metadata.requires_auth if provider else True


def get_connection_display_info(config: ConnectionConfig) -> str:
    provider = _get_provider_or_none(config.db_type)
    if provider is None:
        return config.name
    return str(provider.display_info(config))
