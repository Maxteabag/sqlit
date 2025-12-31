"""Registry for connection picker cloud UI adapters."""

from __future__ import annotations

import logging

from sqlit.domains.connections.ui.screens.connection_picker.cloud_providers.base import (
    CloudProviderUIAdapter,
)

_LOG = logging.getLogger(__name__)
_ADAPTERS: dict[str, CloudProviderUIAdapter] | None = None


def _load_adapters() -> dict[str, CloudProviderUIAdapter]:
    global _ADAPTERS
    if _ADAPTERS is not None:
        return _ADAPTERS
    try:
        from sqlit.domains.connections.ui.screens.connection_picker.cloud_providers.aws import (
            AWSCloudUIAdapter,
        )
        from sqlit.domains.connections.ui.screens.connection_picker.cloud_providers.azure import (
            AzureCloudUIAdapter,
        )
        from sqlit.domains.connections.ui.screens.connection_picker.cloud_providers.gcp import (
            GCPCloudUIAdapter,
        )

        _ADAPTERS = {
            "azure": AzureCloudUIAdapter(),
            "aws": AWSCloudUIAdapter(),
            "gcp": GCPCloudUIAdapter(),
        }
    except ImportError as exc:
        _LOG.exception(
            "Failed to load cloud UI adapters (possible circular import): %s",
            exc,
        )
        _ADAPTERS = {}
    return _ADAPTERS


def get_cloud_ui_adapter(provider_id: str) -> CloudProviderUIAdapter | None:
    adapters = _load_adapters()
    adapter = adapters.get(provider_id)
    if adapter is None:
        _LOG.warning("No cloud UI adapter registered for provider '%s'.", provider_id)
    return adapter
