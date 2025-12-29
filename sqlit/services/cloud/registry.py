"""Cloud provider registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import CloudProvider

# Global registry of cloud providers
_providers: dict[str, CloudProvider] = {}


def register_provider(provider: CloudProvider) -> None:
    """Register a cloud provider.

    Args:
        provider: The provider instance to register.
    """
    _providers[provider.id] = provider


def get_provider(provider_id: str) -> CloudProvider | None:
    """Get a provider by ID.

    Args:
        provider_id: The provider ID (e.g., 'azure', 'aws', 'gcp').

    Returns:
        The provider instance, or None if not found.
    """
    return _providers.get(provider_id)


def get_providers() -> list[CloudProvider]:
    """Get all registered providers in display order.

    Returns:
        List of provider instances.
    """
    # Return in a consistent order: Azure, AWS, GCP, then others
    order = ["azure", "aws", "gcp"]
    result = []
    for provider_id in order:
        if provider_id in _providers:
            result.append(_providers[provider_id])
    # Add any others not in the predefined order
    for provider_id, provider in _providers.items():
        if provider_id not in order:
            result.append(provider)
    return result


def _auto_register_providers() -> None:
    """Auto-register built-in providers."""
    # Import providers to trigger registration
    try:
        from .azure import provider as _  # noqa: F401
    except ImportError:
        pass
    try:
        from .aws import provider as _  # noqa: F401
    except ImportError:
        pass
    try:
        from .gcp import provider as _  # noqa: F401
    except ImportError:
        pass


# Auto-register on module import
_auto_register_providers()
