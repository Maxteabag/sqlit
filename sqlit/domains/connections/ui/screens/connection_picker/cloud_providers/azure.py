"""Azure-specific UI adapter for the cloud connection picker."""

from __future__ import annotations

from typing import Any, cast

from textual.widgets.tree import TreeNode

from sqlit.domains.connections.discovery.cloud import ProviderState, ProviderStatus
from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.ui.screens.connection_picker.cloud_nodes import CloudNodeData
from sqlit.domains.connections.ui.screens.connection_picker.cloud_providers.base import (
    CloudProviderUIAdapter,
)
from sqlit.domains.connections.ui.screens.connection_picker.cloud_providers.utils import (
    format_saved_label,
)
from sqlit.domains.connections.ui.screens.connection_picker.constants import TAB_CLOUD


class AzureCloudUIAdapter(CloudProviderUIAdapter):
    """UI adapter for Azure cloud providers."""

    provider_id = "azure"

    def login_option_id(self, provider: Any) -> str:
        return cast(str, provider.LOGIN_ID)

    def account_option_id(self, provider: Any) -> str:
        return cast(str, provider.ACCOUNT_ID)

    def build_resources(
        self,
        parent: TreeNode,
        provider: Any,
        state: ProviderState,
        connections: list[ConnectionConfig],
        loading_databases: set[str],
    ) -> None:
        subscriptions = state.extra.get("subscriptions", [])
        current_sub_index = state.extra.get("current_subscription_index", 0)
        servers = state.extra.get("servers", [])

        if not subscriptions:
            parent.add_leaf("[dim](no subscriptions)[/]")
            return

        for i, sub in enumerate(subscriptions):
            sub_display = f"{sub.name[:40]}..." if len(sub.name) > 40 else sub.name
            is_active = i == current_sub_index
            label = f"{sub_display}"
            if is_active:
                label = f"{label} [dim](active)[/]"
            sub_node = parent.add(label, expand=is_active)
            sub_node.data = CloudNodeData(provider_id=self.provider_id, option_id=f"{provider.SUB_PREFIX}{i}")

            if not is_active:
                continue

            if not servers:
                sub_node.add_leaf("[dim](no SQL servers)[/]")
                continue

            for server in servers:
                status_suffix = " [dim](Unavailable)[/]" if server.state != "Ready" else ""
                server_node = sub_node.add(f"{server.name}{status_suffix}", expand=True)
                server_node.data = CloudNodeData(provider_id=self.provider_id)

                if not server.databases:
                    server_key = f"{server.name}:{server.resource_group}"
                    if server_key in loading_databases:
                        server_node.add_leaf("[dim](loading databases...)[/]")
                    else:
                        server_node.add_leaf("[dim](no databases)[/]")
                    continue

                for db in server.databases:
                    self._add_database_nodes(
                        server_node,
                        provider,
                        server,
                        db,
                        connections,
                    )

    def on_provider_loaded(self, screen: Any, provider: Any, state: ProviderState) -> None:
        self._auto_load_all_databases(screen, state)

    def switch_subscription(self, screen: Any, provider: Any, subscription_index: int) -> None:
        state = screen._cloud_states.get(provider.id, ProviderState())
        subscriptions = state.extra.get("subscriptions", [])
        current_index = state.extra.get("current_subscription_index", 0)

        if subscription_index == current_index:
            return
        if subscription_index < 0 or subscription_index >= len(subscriptions):
            return

        current_sub = subscriptions[subscription_index]
        screen.notify(f"Loading {current_sub.name}...")
        self._load_provider_for_subscription(screen, provider, current_sub.id, subscription_index)

    def _add_database_nodes(
        self,
        parent: TreeNode,
        provider: Any,
        server: Any,
        database: str,
        connections: list[ConnectionConfig],
    ) -> None:
        if server.has_entra_admin:
            saved = self._is_connection_saved(connections, server, database, False)
            label = format_saved_label(f"{database} [Entra]", saved)
            node = parent.add_leaf(label)
            node.data = CloudNodeData(
                provider_id=self.provider_id,
                option_id=f"{provider.DB_PREFIX}{server.name}:{database}:ad",
            )

        if not server.entra_only_auth:
            saved = self._is_connection_saved(connections, server, database, True)
            label = format_saved_label(f"{database} [SQL Auth]", saved)
            node = parent.add_leaf(label)
            node.data = CloudNodeData(
                provider_id=self.provider_id,
                option_id=f"{provider.DB_PREFIX}{server.name}:{database}:sql",
            )

    def _is_connection_saved(
        self,
        connections: list[ConnectionConfig],
        server: Any,
        database: str,
        use_sql_auth: bool,
    ) -> bool:
        for conn in connections:
            if conn.source != "azure":
                continue
            endpoint = conn.tcp_endpoint
            if endpoint and endpoint.host == server.fqdn and endpoint.database == database:
                conn_is_sql = conn.options.get("auth_type") == "sql"
                if conn_is_sql == use_sql_auth:
                    return True
        return False

    def _auto_load_all_databases(self, screen: Any, state: ProviderState) -> None:
        servers = state.extra.get("servers", [])
        if not servers:
            return

        for server in servers:
            if not hasattr(server, "databases") or server.databases:
                continue

            server_key = f"{server.name}:{server.resource_group}"
            if server_key in screen._loading_databases:
                continue

            screen._loading_databases.add(server_key)
            screen.run_worker(
                lambda s=server: self._load_databases_worker(screen, s),
                thread=True,
            )

        if screen._loading_databases:
            screen._rebuild_list()

    def _load_databases_worker(self, screen: Any, server: Any) -> None:
        from sqlit.domains.connections.discovery.cloud_detector import load_databases_for_server

        databases = load_databases_for_server(server, use_cache=True)
        screen.app.call_from_thread(self._on_databases_loaded, screen, server, databases)

    def _on_databases_loaded(self, screen: Any, server: Any, databases: list[str]) -> None:
        server_key = f"{server.name}:{server.resource_group}"
        screen._loading_databases.discard(server_key)
        server.databases = databases
        screen._rebuild_list()
        if getattr(screen, "_current_tab", "") == TAB_CLOUD:
            screen._rebuild_cloud_tree()
        if not databases:
            screen.notify(f"No databases found on {server.name}", severity="warning")

    def _load_provider_for_subscription(
        self,
        screen: Any,
        provider: Any,
        subscription_id: str,
        new_index: int,
    ) -> None:
        state = screen._cloud_states.get(provider.id, ProviderState())
        state = ProviderState(
            loading=True,
            account=state.account,
            extra={
                **state.extra,
                "current_subscription_index": new_index,
            },
        )
        screen._cloud_states[provider.id] = state
        screen._rebuild_list()

        screen.run_worker(
            lambda: self._discover_subscription_worker(screen, provider, subscription_id, new_index),
            thread=True,
        )

    def _discover_subscription_worker(
        self,
        screen: Any,
        provider: Any,
        subscription_id: str,
        new_index: int,
    ) -> None:
        from sqlit.domains.connections.discovery.cloud_detector import (
            cache_subscriptions_and_servers,
            detect_azure_sql_resources,
        )

        try:
            _status, servers = detect_azure_sql_resources(subscription_id, use_cache=True)
            current_state = screen._cloud_states.get(provider.id, ProviderState())
            subscriptions = current_state.extra.get("subscriptions", [])

            if subscriptions:
                cache_subscriptions_and_servers(subscriptions, servers, subscription_id)

            screen.app.call_from_thread(
                self._on_subscription_loaded,
                screen,
                provider,
                servers,
                subscriptions,
                new_index,
            )
        except Exception as exc:
            screen.app.call_from_thread(screen._on_provider_error, provider.id, str(exc))

    def _on_subscription_loaded(
        self,
        screen: Any,
        provider: Any,
        servers: list,
        subscriptions: list,
        new_index: int,
    ) -> None:
        screen._cloud_states[provider.id] = ProviderState(
            status=ProviderStatus.AVAILABLE,
            account=screen._cloud_states.get(provider.id, ProviderState()).account,
            loading=False,
            extra={
                "subscriptions": subscriptions,
                "servers": servers,
                "current_subscription_index": new_index,
            },
        )

        screen._rebuild_list()
        if getattr(screen, "_current_tab", "") == TAB_CLOUD:
            screen._rebuild_cloud_tree()
        screen._update_shortcuts()
        self._auto_load_all_databases(screen, screen._cloud_states[provider.id])
