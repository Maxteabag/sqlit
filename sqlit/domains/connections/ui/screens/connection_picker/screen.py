"""Connection picker screen with fuzzy search and Docker/Cloud detection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import OptionList, Tree
from textual.widgets.option_list import Option
from textual.widgets.tree import TreeNode

from sqlit.domains.connections.app.cloud_actions import (
    CloudActionRequest,
    CloudActionResponse,
    CloudActionService,
)
from sqlit.domains.connections.app.save_connection import is_config_saved, save_connection
from sqlit.domains.connections.discovery.cloud import ProviderState, get_providers
from sqlit.domains.explorer.ui.tree import builder as tree_builder
from sqlit.shared.core.utils import fuzzy_match
from sqlit.shared.ui.protocols import AppProtocol
from sqlit.shared.ui.widgets import Dialog, FilterInput

from .cloud_nodes import CloudNodeData
from .cloud_providers import get_cloud_ui_adapter
from .controllers.cloud import CloudController
from .controllers.docker import DockerController
from .constants import TAB_CLOUD, TAB_CONNECTIONS, TAB_DOCKER
from .state import CloudState, DockerState, FilterState
from .tabs import (
    DOCKER_PREFIX,
    find_connection_by_name,
    find_container_by_id,
    find_matching_saved_connection,
    is_container_saved,
    is_docker_option_id,
)
from .view import PickerView

if TYPE_CHECKING:
    from sqlit.domains.connections.discovery.docker_detector import DetectedContainer, DockerStatus
    from sqlit.domains.connections.domain.config import ConnectionConfig


class ConnectionPickerScreen(ModalScreen):
    """Modal screen for selecting a connection with fuzzy search."""

    BINDINGS = [
        Binding("escape", "cancel_or_close_filter", "Cancel"),
        Binding("enter", "select", "Select"),
        Binding("s", "save", "Save", show=False),
        Binding("n", "new_connection", "New", show=False),
        Binding("f", "refresh", "Refresh", show=False),
        Binding("slash", "open_filter", "Search", show=False),
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("backspace", "backspace", "Backspace", show=False),
        Binding("tab", "switch_tab", "Switch Tab", show=False),
        Binding("l", "cloud_logout", "Logout", show=False),
        Binding("w", "cloud_switch", "Switch", show=False),
    ]

    CSS = """
    ConnectionPickerScreen {
        align: center middle;
        background: transparent;
    }

    #picker-dialog {
        width: 75;
        max-width: 90%;
        height: auto;
        max-height: 70%;
    }

    #picker-list {
        height: 20;
        background: $surface;
        border: none;
        padding: 0;
    }

    #picker-list > .option-list--option {
        padding: 0 1;
    }

    #picker-empty {
        text-align: center;
        color: $text-muted;
        padding: 2;
    }

    .section-header {
        color: $text-muted;
        padding: 0 1;
        margin-top: 1;
    }

    .section-header-first {
        color: $text-muted;
        padding: 0 1;
    }

    #picker-filter {
        height: 1;
        background: $surface;
        padding: 0 1;
        margin-bottom: 1;
    }

    #cloud-tree {
        height: 20;
        scrollbar-size: 1 1;
        display: none;
    }

    #cloud-tree.visible {
        display: block;
    }

    #picker-list.hidden {
        display: none;
    }
    """

    def __init__(self, connections: list[ConnectionConfig]):
        super().__init__()
        self.connections = connections
        self._filter_state = FilterState()
        self._current_tab = TAB_CONNECTIONS

        self._cloud_providers = get_providers()
        self._cloud_state = CloudState(
            states={p.id: ProviderState() for p in self._cloud_providers},
        )
        self._cloud_states: dict[str, ProviderState] = self._cloud_state.states
        self._loading_databases: set[str] = self._cloud_state.loading_databases
        self._cloud_actions = CloudActionService(self._cloud_providers)
        self._cloud_ui_adapters = {
            provider.id: get_cloud_ui_adapter(provider.id)
            for provider in self._cloud_providers
        }
        self._docker_state = DockerState()
        self._view = PickerView(self)
        self._docker_controller = DockerController(self, self._docker_state)
        self._cloud_controller = CloudController(self)

    def compose(self) -> ComposeResult:
        with Dialog(id="picker-dialog", title="Connect"):
            yield FilterInput(id="picker-filter")
            yield OptionList(id="picker-list")
            yield Tree("Cloud", id="cloud-tree")

    def on_mount(self) -> None:
        self._update_dialog_title()
        self._rebuild_list()
        if not getattr(self.app, "is_headless", False):
            self._load_containers_async()
            self._load_cloud_providers_async()
        self._update_shortcuts()

    def _app(self) -> AppProtocol:
        return cast(AppProtocol, self.app)

    def _update_dialog_title(self) -> None:
        self._view.update_dialog_title(self._current_tab)

    def _update_shortcuts(self) -> None:
        self._view.update_shortcuts(
            current_tab=self._current_tab,
            providers=self._cloud_providers,
            cloud_states=self._cloud_states,
            cloud_actions=self._cloud_actions,
            connections=self.connections,
            docker_containers=self._docker_state.containers,
        )

    def _get_highlighted_option(self) -> Option | None:
        return self._view.get_highlighted_option()

    def _get_highlighted_tree_node(self) -> TreeNode | None:
        return self._view.get_highlighted_tree_node()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id == "picker-list":
            self._update_shortcuts()

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted) -> None:
        if event.control.id == "cloud-tree":
            self._update_shortcuts()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "picker-list":
            self.action_select()

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        if event.control.id != "cloud-tree":
            return
        result = self._select_cloud_node()
        if result is not None:
            self.dismiss(result)

    def _load_containers_async(self) -> None:
        self._docker_controller.load_async()

    def _on_containers_loaded(self, status: DockerStatus, containers: list[DetectedContainer]) -> None:
        self._docker_controller.on_containers_loaded(status, containers)

    def _load_cloud_providers_async(self) -> None:
        self._cloud_controller.load_providers_async()

    def _discover_provider_worker(self, provider: Any) -> None:
        self._cloud_controller.discover_provider_worker(provider)

    def _on_provider_loaded(self, provider_id: str, state: ProviderState) -> None:
        self._cloud_controller.on_provider_loaded(provider_id, state)

    def _on_provider_error(self, provider_id: str, error: str) -> None:
        self._cloud_controller.on_provider_error(provider_id, error)

    def _start_provider_login(self, provider_id: str) -> None:
        self._cloud_controller.start_provider_login(provider_id)

    def _provider_login_worker(self, provider: Any) -> None:
        self._cloud_controller.provider_login_worker(provider)

    def _on_provider_login_complete(self, provider: Any, success: bool) -> None:
        self._cloud_controller.on_provider_login_complete(provider, success)

    def _on_provider_login_error(self, provider: Any, error: str) -> None:
        self._cloud_controller.on_provider_login_error(provider, error)

    def _start_provider_logout(self, provider_id: str) -> None:
        self._cloud_controller.start_provider_logout(provider_id)

    def _provider_logout_worker(self, provider: Any) -> None:
        self._cloud_controller.provider_logout_worker(provider)

    def _on_provider_logout_complete(self, provider: Any, success: bool) -> None:
        self._cloud_controller.on_provider_logout_complete(provider, success)

    def action_cloud_logout(self) -> None:
        self._handle_cloud_action("logout")

    def action_cloud_switch(self) -> None:
        self._handle_cloud_action("switch")

    def _rebuild_list(self) -> None:
        self._view.rebuild_list(
            current_tab=self._current_tab,
            connections=self.connections,
            search_text=self._filter_state.text,
            docker_containers=self._docker_state.containers,
            loading_docker=self._docker_state.loading,
            docker_status_message=self._docker_state.status_message,
        )

    def _update_list(self) -> None:
        self._rebuild_list()
        self._update_shortcuts()

    def _rebuild_cloud_tree(self) -> None:
        self._view.rebuild_cloud_tree(
            providers=self._cloud_providers,
            states=self._cloud_states,
            connections=self.connections,
            loading_databases=self._loading_databases,
        )

    def on_key(self, event: Key) -> None:
        if not self._filter_state.active:
            return

        key = event.key
        if key == "backspace":
            if self._filter_state.text:
                self._filter_state.text = self._filter_state.text[:-1]
                self._update_filter_display()
                self._update_list()
            else:
                self._close_filter()
            event.prevent_default()
            event.stop()
            return

        if event.character and event.character.isprintable():
            self._filter_state.text += event.character
            self._update_filter_display()
            self._update_list()
            event.prevent_default()
            event.stop()

    def action_backspace(self) -> None:
        if not self._filter_state.active:
            return
        pass

    def action_open_filter(self) -> None:
        self._filter_state.active = True
        self._filter_state.text = ""
        self._view.show_filter()
        self._update_filter_display()

    def _close_filter(self) -> None:
        self._filter_state.active = False
        self._filter_state.text = ""
        self._view.hide_filter()
        self._update_list()

    def _update_filter_display(self) -> None:
        total = len(self.connections) + len(self._docker_state.containers)
        if self._filter_state.text:
            match_count = self._count_matches()
            self._view.set_filter_display(self._filter_state.text, match_count, total)
        else:
            self._view.set_filter_display("", 0, total)

    def _count_matches(self) -> int:
        count = 0
        pattern = self._filter_state.text
        for conn in self.connections:
            matches, _ = fuzzy_match(pattern, conn.name)
            if matches:
                count += 1
        for container in self._docker_state.containers:
            matches, _ = fuzzy_match(pattern, container.container_name)
            if matches:
                count += 1
        return count

    def action_cancel_or_close_filter(self) -> None:
        if self._filter_state.active:
            self._close_filter()
        else:
            self.dismiss(None)

    def action_move_up(self) -> None:
        if self._current_tab == TAB_CLOUD:
            try:
                tree = self.query_one("#cloud-tree", Tree)
                handler = getattr(tree, "action_cursor_up", None)
                if callable(handler):
                    handler()
                elif tree.cursor_line is not None:
                    tree.cursor_line = max(0, tree.cursor_line - 1)
            except Exception:
                pass
            return
        try:
            option_list = self.query_one("#picker-list", OptionList)
            current = option_list.highlighted
            if current is None:
                return
            for i in range(current - 1, -1, -1):
                option = option_list.get_option_at_index(i)
                if option and not option.disabled:
                    option_list.highlighted = i
                    return
        except Exception:
            pass

    def action_move_down(self) -> None:
        if self._current_tab == TAB_CLOUD:
            try:
                tree = self.query_one("#cloud-tree", Tree)
                handler = getattr(tree, "action_cursor_down", None)
                if callable(handler):
                    handler()
                elif tree.cursor_line is not None:
                    line_count = getattr(tree, "line_count", None)
                    next_line = tree.cursor_line + 1
                    if isinstance(line_count, int):
                        next_line = min(next_line, max(0, line_count - 1))
                    tree.cursor_line = next_line
            except Exception:
                pass
            return
        try:
            option_list = self.query_one("#picker-list", OptionList)
            current = option_list.highlighted
            if current is None:
                return
            for i in range(current + 1, option_list.option_count):
                option = option_list.get_option_at_index(i)
                if option and not option.disabled:
                    option_list.highlighted = i
                    return
        except Exception:
            pass

    def action_select(self) -> None:
        if self._current_tab == TAB_CLOUD:
            result = self._select_cloud_node()
            if result is not None:
                self.dismiss(result)
            return

        option = self._get_highlighted_option()
        if not option or option.disabled:
            return

        option_id = str(option.id) if option.id else ""
        if is_docker_option_id(option_id):
            container_id = option_id[len(DOCKER_PREFIX):]
            container = find_container_by_id(self._docker_state.containers, container_id)
            if container:
                if not container.is_running:
                    self.notify("Container is not running", severity="warning")
                    return
                from sqlit.domains.connections.discovery.docker_detector import (
                    container_to_connection_config,
                )

                existing = find_matching_saved_connection(self.connections, container)
                docker_config = existing or container_to_connection_config(container)
                self.dismiss(docker_config)
            return

        saved_config = find_connection_by_name(self.connections, option_id)
        if saved_config:
            self.dismiss(saved_config)

    def _select_cloud_node(self) -> Any | None:
        tree_node = self._get_highlighted_tree_node()
        return self._cloud_controller.select_node(tree_node, self.connections)

    def _handle_cloud_action(self, action: str) -> None:
        if self._current_tab != TAB_CLOUD:
            return
        tree_node = self._get_highlighted_tree_node()
        self._cloud_controller.handle_action(action, tree_node, self.connections)

    def _handle_cloud_action_response(
        self,
        provider_id: str,
        response: CloudActionResponse,
    ) -> ConnectionConfig | None:
        return self._cloud_controller.handle_action_response(provider_id, response)

    def _switch_cloud_subscription(self, provider_id: str, index: int) -> None:
        self._cloud_controller.switch_subscription(provider_id, index)

    def action_switch_tab(self) -> None:
        if self._current_tab == TAB_CONNECTIONS:
            self._current_tab = TAB_DOCKER
        elif self._current_tab == TAB_DOCKER:
            self._current_tab = TAB_CLOUD
        else:
            self._current_tab = TAB_CONNECTIONS

        self._update_dialog_title()
        self._update_widget_visibility()
        self._rebuild_list()
        self._update_shortcuts()

    def _update_widget_visibility(self) -> None:
        self._view.set_tab_visibility(
            current_tab=self._current_tab,
            providers=self._cloud_providers,
            states=self._cloud_states,
            connections=self.connections,
            loading_databases=self._loading_databases,
        )

    def action_new_connection(self) -> None:
        self.dismiss("__new_connection__")

    def action_refresh(self) -> None:
        from sqlit.domains.connections.discovery.cloud.aws.cache import clear_aws_cache
        from sqlit.domains.connections.discovery.cloud.gcp.cache import clear_gcp_cache
        from sqlit.domains.connections.discovery.cloud.azure.cache import clear_azure_cache

        clear_azure_cache()
        clear_aws_cache()
        clear_gcp_cache()

        self._load_containers_async()
        self._load_cloud_providers_async()
        self.notify("Refreshing...")

    def action_save(self) -> None:
        if self._current_tab == TAB_CLOUD:
            self._save_cloud_selection()
            return

        option = self._get_highlighted_option()
        if not option or option.disabled:
            return

        option_id = str(option.id) if option.id else ""
        if is_docker_option_id(option_id):
            container_id = option_id[len(DOCKER_PREFIX):]
            container = find_container_by_id(self._docker_state.containers, container_id)
            if container:
                if is_container_saved(self.connections, container):
                    self.notify("Container already saved", severity="warning")
                    return
                from sqlit.domains.connections.discovery.docker_detector import (
                    container_to_connection_config,
                )

                config = container_to_connection_config(container)
                self._save_connection_and_refresh(config, option_id)
            return

    def _save_cloud_selection(self) -> None:
        tree_node = self._get_highlighted_tree_node()
        if not tree_node or not tree_node.data:
            return
        data = tree_node.data
        if not isinstance(data, CloudNodeData) or not data.option_id:
            return
        provider_id = data.provider_id
        option_id = data.option_id
        state = self._cloud_states.get(provider_id, ProviderState())
        response = self._cloud_actions.handle(
            CloudActionRequest(provider_id, "save", option_id),
            state=state,
            connections=self.connections,
        )
        config = self._handle_cloud_action_response(provider_id, response)
        if response.action == "save" and config:
            if is_config_saved(self.connections, config):
                self.notify("Connection already saved", severity="warning")
                return
            self._save_connection_and_refresh(config, option_id)
        elif response.action == "none":
            self.notify("Connection already saved", severity="warning")

    def _save_connection_and_refresh(self, config: ConnectionConfig, option_id: str) -> None:
        result = save_connection(self.connections, self._app().services.connection_store, config)
        if result.warning:
            if result.warning_severity == "error":
                from sqlit.shared.ui.screens.error import ErrorScreen

                self.push_screen(ErrorScreen("Keyring Error", result.warning))
            else:
                self.notify(result.warning, severity=result.warning_severity)
        if result.saved:
            self.notify(result.message)
        else:
            self.notify(result.message, severity="error")
            return

        self._rebuild_list()
        tree_builder.refresh_tree(cast(Any, self.app))

        if self._current_tab == TAB_DOCKER:
            self._select_option_by_id(option_id)
        elif self._current_tab == TAB_CLOUD:
            self._rebuild_cloud_tree()
        self._update_shortcuts()

    def _select_option_by_id(self, option_id: str) -> None:
        self._view.select_option_by_id(option_id)
