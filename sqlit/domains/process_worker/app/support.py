"""Helpers for deciding process worker availability."""

from __future__ import annotations

from typing import Any


def supports_process_worker(provider: Any) -> bool:
    """Return False when a provider or adapter opts out of process workers."""
    adapter = getattr(provider, "connection_factory", None)
    for candidate in (adapter, provider):
        value = getattr(candidate, "supports_process_worker", None)
        if isinstance(value, bool):
            return value
    return True
