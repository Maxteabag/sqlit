"""Cloud provider abstractions for database discovery.

This module provides a plugin-based architecture for cloud database discovery,
supporting Azure, AWS, GCP, and potentially other cloud providers.
"""

from .base import (
    AccountInfo,
    CloudProvider,
    CloudResource,
    ProviderState,
    ProviderStatus,
    SelectionResult,
)
from .registry import get_provider, get_providers, register_provider

__all__ = [
    "AccountInfo",
    "CloudProvider",
    "CloudResource",
    "ProviderState",
    "ProviderStatus",
    "SelectionResult",
    "get_provider",
    "get_providers",
    "register_provider",
]
