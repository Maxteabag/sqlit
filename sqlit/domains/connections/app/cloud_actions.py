"""Cloud action routing for connection picker flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlit.domains.connections.discovery.cloud import CloudProvider, ProviderState, SelectionResult
from sqlit.domains.connections.domain.config import ConnectionConfig


@dataclass(frozen=True)
class CloudActionRequest:
    provider_id: str
    action: str
    option_id: str


@dataclass
class CloudActionResponse:
    action: str
    config: ConnectionConfig | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class CloudActionService:
    """UI-agnostic cloud action dispatcher."""

    def __init__(self, providers: list[CloudProvider]) -> None:
        self._providers = {provider.id: provider for provider in providers}

    def get_provider(self, provider_id: str) -> CloudProvider | None:
        return self._providers.get(provider_id)

    def handle(
        self,
        request: CloudActionRequest,
        *,
        state: ProviderState,
        connections: list[ConnectionConfig],
    ) -> CloudActionResponse:
        provider = self._providers.get(request.provider_id)
        if provider is None:
            return CloudActionResponse(action="none")
        result: SelectionResult = provider.handle_action(
            request.action,
            request.option_id,
            state,
            connections,
        )
        return CloudActionResponse(
            action=result.action,
            config=result.config,
            metadata=dict(result.metadata),
        )

    def login(self, provider_id: str) -> bool:
        provider = self._providers.get(provider_id)
        if provider is None:
            return False
        return provider.login()

    def logout(self, provider_id: str) -> bool:
        provider = self._providers.get(provider_id)
        if provider is None:
            return False
        return provider.logout()
