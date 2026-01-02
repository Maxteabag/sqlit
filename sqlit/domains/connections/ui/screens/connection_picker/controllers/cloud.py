"""Cloud discovery controller for the connection picker."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlit.domains.connections.app.cloud_actions import (
    CloudActionRequest,
    CloudActionResponse,
)
from sqlit.domains.connections.discovery.cloud import ProviderState, ProviderStatus
from sqlit.domains.connections.ui.screens.connection_picker.cloud_nodes import CloudNodeData
from sqlit.domains.connections.ui.screens.connection_picker.constants import TAB_CLOUD

if TYPE_CHECKING:
    from textual.widgets.tree import TreeNode

    from sqlit.domains.connections.domain.config import ConnectionConfig
    from sqlit.domains.connections.ui.screens.connection_picker.screen import ConnectionPickerScreen


class CloudController:
    """Handle cloud discovery, login/logout, and selection actions."""

    def __init__(self, screen: ConnectionPickerScreen) -> None:
        self._screen = screen

    def load_providers_async(self) -> None:
        seed_states = self._screen._app().services.cloud_discovery.load_seed_states(
            self._screen._cloud_providers
        )
        if seed_states is not None:
            for provider in self._screen._cloud_providers:
                if provider.id in seed_states:
                    self._screen._cloud_states[provider.id] = seed_states[provider.id]
            self._screen._rebuild_list()
            if self._screen._current_tab == TAB_CLOUD:
                self._screen._rebuild_cloud_tree()
            self._screen._update_shortcuts()
            return

        for provider in self._screen._cloud_providers:
            self._screen._cloud_states[provider.id] = ProviderState(loading=True)

        self._screen._rebuild_list()

        for provider in self._screen._cloud_providers:
            self._screen.run_worker(
                lambda p=provider: self.discover_provider_worker(p),
                thread=True,
            )

    def discover_provider_worker(self, provider: Any) -> None:
        try:
            state = ProviderState(loading=True)
            new_state = self._screen._app().services.cloud_discovery.discover(provider, state)
            self._screen.app.call_from_thread(self.on_provider_loaded, provider.id, new_state)
        except Exception as exc:
            self._screen.app.call_from_thread(self.on_provider_error, provider.id, str(exc))

    def on_provider_loaded(self, provider_id: str, state: ProviderState) -> None:
        self._screen._cloud_states[provider_id] = state
        self._screen._rebuild_list()
        if self._screen._current_tab == TAB_CLOUD:
            self._screen._rebuild_cloud_tree()
        self._screen._update_shortcuts()

        adapter = self._screen._cloud_ui_adapters.get(provider_id)
        provider = self._screen._cloud_actions.get_provider(provider_id)
        if adapter is not None and provider is not None:
            adapter.on_provider_loaded(self._screen, provider, state)

    def on_provider_error(self, provider_id: str, error: str) -> None:
        self._screen._cloud_states[provider_id] = ProviderState(
            status=ProviderStatus.ERROR,
            loading=False,
            error=error,
        )
        self._screen._rebuild_list()
        if self._screen._current_tab == TAB_CLOUD:
            self._screen._rebuild_cloud_tree()
        self._screen.notify(f"Cloud error: {error}", severity="error")

    def start_provider_login(self, provider_id: str) -> None:
        provider = self._screen._cloud_actions.get_provider(provider_id)
        if provider is None:
            return
        self._screen.notify(f"Opening browser for {provider.name} login...")
        self._screen._cloud_states[provider.id] = ProviderState(loading=True)
        self._screen._rebuild_list()
        self._screen.run_worker(
            lambda: self.provider_login_worker(provider),
            thread=True,
        )

    def provider_login_worker(self, provider: Any) -> None:
        try:
            success = self._screen._cloud_actions.login(provider.id)
            self._screen.app.call_from_thread(self.on_provider_login_complete, provider, success)
        except Exception as exc:
            self._screen.app.call_from_thread(self.on_provider_login_error, provider, str(exc))

    def on_provider_login_complete(self, provider: Any, success: bool) -> None:
        if success:
            self._screen.notify(f"{provider.name} login successful. Loading resources...")
            self._screen._cloud_states[provider.id] = ProviderState(loading=True)
            self._screen._rebuild_list()
            if self._screen._current_tab == TAB_CLOUD:
                self._screen._rebuild_cloud_tree()
            self._screen.run_worker(
                lambda: self.discover_provider_worker(provider),
                thread=True,
            )
        else:
            self._screen._cloud_states[provider.id] = ProviderState(
                status=ProviderStatus.NOT_LOGGED_IN,
                loading=False,
            )
            self._screen._rebuild_list()
            if self._screen._current_tab == TAB_CLOUD:
                self._screen._rebuild_cloud_tree()
            self._screen.notify(f"{provider.name} login failed", severity="error")

    def on_provider_login_error(self, provider: Any, error: str) -> None:
        self._screen._cloud_states[provider.id] = ProviderState(
            status=ProviderStatus.ERROR,
            loading=False,
            error=error,
        )
        self._screen._rebuild_list()
        if self._screen._current_tab == TAB_CLOUD:
            self._screen._rebuild_cloud_tree()
        self._screen.notify(f"{provider.name} login failed: {error}", severity="error")

    def start_provider_logout(self, provider_id: str) -> None:
        provider = self._screen._cloud_actions.get_provider(provider_id)
        if provider is None:
            return
        self._screen.notify(f"Logging out from {provider.name}...")
        self._screen._cloud_states[provider.id] = ProviderState(loading=True)
        self._screen._rebuild_list()
        self._screen.run_worker(
            lambda: self.provider_logout_worker(provider),
            thread=True,
        )

    def provider_logout_worker(self, provider: Any) -> None:
        success = self._screen._cloud_actions.logout(provider.id)
        self._screen.app.call_from_thread(self.on_provider_logout_complete, provider, success)

    def on_provider_logout_complete(self, provider: Any, success: bool) -> None:
        if success:
            self._screen._cloud_states[provider.id] = ProviderState(
                status=ProviderStatus.NOT_LOGGED_IN,
                loading=False,
            )
            self._screen.notify(f"Logged out from {provider.name}")
        else:
            self._screen._cloud_states[provider.id] = ProviderState(
                status=ProviderStatus.ERROR,
                loading=False,
                error="Logout failed",
            )
            self._screen.notify(f"Failed to logout from {provider.name}", severity="warning")

        self._screen._rebuild_list()
        if self._screen._current_tab == TAB_CLOUD:
            self._screen._rebuild_cloud_tree()

    def select_node(
        self,
        tree_node: TreeNode | None,
        connections: list[ConnectionConfig],
    ) -> ConnectionConfig | None:
        data = self._extract_node_data(tree_node)
        if data is None:
            return None
        provider_id, option_id = data
        state = self._screen._cloud_states.get(provider_id, ProviderState())
        response = self._screen._cloud_actions.handle(
            CloudActionRequest(provider_id, "select", option_id),
            state=state,
            connections=connections,
        )
        config = self.handle_action_response(provider_id, response)
        if response.action == "connect":
            return config
        return None

    def handle_action(
        self,
        action: str,
        tree_node: TreeNode | None,
        connections: list[ConnectionConfig],
    ) -> None:
        data = self._extract_node_data(tree_node)
        if data is None:
            return
        provider_id, option_id = data
        state = self._screen._cloud_states.get(provider_id, ProviderState())
        response = self._screen._cloud_actions.handle(
            CloudActionRequest(provider_id, action, option_id),
            state=state,
            connections=connections,
        )
        self.handle_action_response(provider_id, response)

    def handle_action_response(
        self,
        provider_id: str,
        response: CloudActionResponse,
    ) -> ConnectionConfig | None:
        if response.action == "login":
            self.start_provider_login(provider_id)
            return None
        if response.action == "logout":
            self.start_provider_logout(provider_id)
            return None
        if response.action == "switch_subscription":
            index = int(response.metadata.get("subscription_index", 0))
            self.switch_subscription(provider_id, index)
            return None
        if response.action in ("connect", "save"):
            return response.config
        return None

    def switch_subscription(self, provider_id: str, index: int) -> None:
        adapter = self._screen._cloud_ui_adapters.get(provider_id)
        provider = self._screen._cloud_actions.get_provider(provider_id)
        if adapter is None or provider is None:
            return
        adapter.switch_subscription(self._screen, provider, index)

    def _extract_node_data(self, tree_node: TreeNode | None) -> tuple[str, str] | None:
        if not tree_node or not tree_node.data:
            return None
        data = tree_node.data
        if not isinstance(data, CloudNodeData) or not data.option_id:
            return None
        return data.provider_id, data.option_id
