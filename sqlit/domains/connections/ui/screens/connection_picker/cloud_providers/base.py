"""Cloud provider UI adapters for the connection picker."""

from __future__ import annotations

from typing import Any, Protocol

from textual.widgets.tree import TreeNode

from sqlit.domains.connections.discovery.cloud import ProviderState
from sqlit.domains.connections.domain.config import ConnectionConfig


class CloudProviderUIAdapter(Protocol):
    """Protocol for provider-specific cloud UI behavior."""

    provider_id: str

    def login_option_id(self, provider: Any) -> str:
        ...

    def account_option_id(self, provider: Any) -> str:
        ...

    def build_resources(
        self,
        parent: TreeNode,
        provider: Any,
        state: ProviderState,
        connections: list[ConnectionConfig],
        loading_databases: set[str],
    ) -> None:
        ...

    def on_provider_loaded(self, screen: Any, provider: Any, state: ProviderState) -> None:
        ...

    def switch_subscription(
        self,
        screen: Any,
        provider: Any,
        subscription_index: int,
    ) -> None:
        ...
