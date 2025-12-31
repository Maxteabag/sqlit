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
from sqlit.domains.connections.discovery.cloud import ProviderState, ProviderStatus, get_providers
from sqlit.shared.core.utils import fuzzy_match
from sqlit.shared.ui.protocols import AppProtocol
from sqlit.shared.ui.widgets import Dialog, FilterInput

from .cloud_nodes import CloudNodeData
from .cloud_providers import get_cloud_ui_adapter
from .constants import TAB_CLOUD, TAB_CONNECTIONS, TAB_DOCKER
from .shortcuts import build_picker_shortcuts
from .tabs import (
    DOCKER_PREFIX,
    build_cloud_tree,
    build_connections_options,
    build_docker_options,
    find_connection_by_name,
    find_container_by_id,
    find_matching_saved_connection,
    is_container_saved,
    is_docker_option_id,
)

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
        self.search_text = ""
        self._filter_active = False
        self._current_tab = TAB_CONNECTIONS

        self._docker_containers: list[DetectedContainer] = []
        self._docker_status_message: str | None = None
        self._loading_docker = False

        self._loading_databases: set[str] = set()
        self._cloud_providers = get_providers()
        self._cloud_states: dict[str, ProviderState] = {
            p.id: ProviderState() for p in self._cloud_providers
        }
        self._cloud_actions = CloudActionService(self._cloud_providers)
        self._cloud_ui_adapters = {
            provider.id: get_cloud_ui_adapter(provider.id)
            for provider in self._cloud_providers
        }

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
        dialog = self.query_one("#picker-dialog", Dialog)
        if self._current_tab == TAB_CONNECTIONS:
            dialog.border_title = "[bold]Connections[/] | [dim]Docker[/] | [dim]Cloud[/]  [dim]<tab>[/]"
        elif self._current_tab == TAB_DOCKER:
            dialog.border_title = "[dim]Connections[/] | [bold]Docker[/] | [dim]Cloud[/]  [dim]<tab>[/]"
        else:
            dialog.border_title = "[dim]Connections[/] | [dim]Docker[/] | [bold]Cloud[/]  [dim]<tab>[/]"

    def _update_shortcuts(self) -> None:
        dialog = self.query_one("#picker-dialog", Dialog)
        option = self._get_highlighted_option()
        tree_node = self._get_highlighted_tree_node()
        shortcuts = build_picker_shortcuts(
            current_tab=self._current_tab,
            option=option,
            tree_node=tree_node,
            providers=self._cloud_providers,
            cloud_states=self._cloud_states,
            cloud_actions=self._cloud_actions,
            connections=self.connections,
            docker_containers=self._docker_containers,
        )
        dialog.border_subtitle = " ".join(f"{label}: <{key}>" for label, key in shortcuts)

    def _get_highlighted_option(self) -> Option | None:
        try:
            option_list = self.query_one("#picker-list", OptionList)
            highlighted = option_list.highlighted
            if highlighted is not None:
                return option_list.get_option_at_index(highlighted)
        except Exception:
            pass
        return None

    def _get_highlighted_tree_node(self) -> TreeNode | None:
        try:
            tree = self.query_one("#cloud-tree", Tree)
            return tree.cursor_node
        except Exception:
            pass
        return None

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
        self._loading_docker = True
        self._rebuild_list()
        self.run_worker(self._detect_docker_worker, thread=True)

    def _detect_docker_worker(self) -> None:
        status, containers = self._app().services.docker_detector()
        self.app.call_from_thread(self._on_containers_loaded, status, containers)

    def _on_containers_loaded(self, status: DockerStatus, containers: list[DetectedContainer]) -> None:
        from sqlit.domains.connections.discovery.docker_detector import DockerStatus

        self._loading_docker = False
        self._docker_containers = containers

        if status == DockerStatus.NOT_INSTALLED:
            self._docker_status_message = "(Docker not detected)"
        elif status == DockerStatus.NOT_RUNNING:
            self._docker_status_message = "(Docker not running)"
        elif status == DockerStatus.NOT_ACCESSIBLE:
            self._docker_status_message = "(Docker not accessible)"
        elif status == DockerStatus.AVAILABLE and not containers:
            self._docker_status_message = "(no database containers found)"
        else:
            self._docker_status_message = None

        self._rebuild_list()
        self._update_shortcuts()

    def _load_cloud_providers_async(self) -> None:
        seed_states = self._app().services.cloud_discovery.load_seed_states(self._cloud_providers)
        if seed_states is not None:
            for provider in self._cloud_providers:
                if provider.id in seed_states:
                    self._cloud_states[provider.id] = seed_states[provider.id]
            self._rebuild_list()
            if self._current_tab == TAB_CLOUD:
                self._rebuild_cloud_tree()
            self._update_shortcuts()
            return

        for provider in self._cloud_providers:
            self._cloud_states[provider.id] = ProviderState(loading=True)

        self._rebuild_list()

        for provider in self._cloud_providers:
            self.run_worker(
                lambda p=provider: self._discover_provider_worker(p),
                thread=True,
            )

    def _discover_provider_worker(self, provider: Any) -> None:
        try:
            state = ProviderState(loading=True)
            new_state = self._app().services.cloud_discovery.discover(provider, state)
            self.app.call_from_thread(self._on_provider_loaded, provider.id, new_state)
        except Exception as exc:
            self.app.call_from_thread(self._on_provider_error, provider.id, str(exc))

    def _on_provider_loaded(self, provider_id: str, state: ProviderState) -> None:
        self._cloud_states[provider_id] = state
        self._rebuild_list()
        if self._current_tab == TAB_CLOUD:
            self._rebuild_cloud_tree()
        self._update_shortcuts()

        adapter = self._cloud_ui_adapters.get(provider_id)
        provider = self._cloud_actions.get_provider(provider_id)
        if adapter is not None and provider is not None:
            adapter.on_provider_loaded(self, provider, state)

    def _on_provider_error(self, provider_id: str, error: str) -> None:
        self._cloud_states[provider_id] = ProviderState(
            status=ProviderStatus.ERROR,
            loading=False,
            error=error,
        )
        self._rebuild_list()
        if self._current_tab == TAB_CLOUD:
            self._rebuild_cloud_tree()
        self.notify(f"Cloud error: {error}", severity="error")

    def _start_provider_login(self, provider_id: str) -> None:
        provider = self._cloud_actions.get_provider(provider_id)
        if provider is None:
            return
        self.notify(f"Opening browser for {provider.name} login...")
        self._cloud_states[provider.id] = ProviderState(loading=True)
        self._rebuild_list()
        self.run_worker(
            lambda: self._provider_login_worker(provider),
            thread=True,
        )

    def _provider_login_worker(self, provider: Any) -> None:
        try:
            success = self._cloud_actions.login(provider.id)
            self.app.call_from_thread(self._on_provider_login_complete, provider, success)
        except Exception as exc:
            self.app.call_from_thread(self._on_provider_login_error, provider, str(exc))

    def _on_provider_login_complete(self, provider: Any, success: bool) -> None:
        if success:
            self.notify(f"{provider.name} login successful. Loading resources...")
            self._cloud_states[provider.id] = ProviderState(loading=True)
            self._rebuild_list()
            if self._current_tab == TAB_CLOUD:
                self._rebuild_cloud_tree()
            self.run_worker(
                lambda: self._discover_provider_worker(provider),
                thread=True,
            )
        else:
            self._cloud_states[provider.id] = ProviderState(
                status=ProviderStatus.NOT_LOGGED_IN,
                loading=False,
            )
            self._rebuild_list()
            if self._current_tab == TAB_CLOUD:
                self._rebuild_cloud_tree()
            self.notify(f"{provider.name} login failed", severity="error")

    def _on_provider_login_error(self, provider: Any, error: str) -> None:
        self._cloud_states[provider.id] = ProviderState(
            status=ProviderStatus.ERROR,
            loading=False,
            error=error,
        )
        self._rebuild_list()
        if self._current_tab == TAB_CLOUD:
            self._rebuild_cloud_tree()
        self.notify(f"{provider.name} login failed: {error}", severity="error")

    def _start_provider_logout(self, provider_id: str) -> None:
        provider = self._cloud_actions.get_provider(provider_id)
        if provider is None:
            return
        self.notify(f"Logging out from {provider.name}...")
        self._cloud_states[provider.id] = ProviderState(loading=True)
        self._rebuild_list()
        self.run_worker(
            lambda: self._provider_logout_worker(provider),
            thread=True,
        )

    def _provider_logout_worker(self, provider: Any) -> None:
        success = self._cloud_actions.logout(provider.id)
        self.app.call_from_thread(self._on_provider_logout_complete, provider, success)

    def _on_provider_logout_complete(self, provider: Any, success: bool) -> None:
        if success:
            self._cloud_states[provider.id] = ProviderState(
                status=ProviderStatus.NOT_LOGGED_IN,
                loading=False,
            )
            self.notify(f"Logged out from {provider.name}")
        else:
            self._cloud_states[provider.id] = ProviderState(
                status=ProviderStatus.ERROR,
                loading=False,
                error="Logout failed",
            )
            self.notify(f"Failed to logout from {provider.name}", severity="warning")

        self._rebuild_list()
        if self._current_tab == TAB_CLOUD:
            self._rebuild_cloud_tree()

    def action_cloud_logout(self) -> None:
        self._handle_cloud_action("logout")

    def action_cloud_switch(self) -> None:
        self._handle_cloud_action("switch")

    def _rebuild_list(self) -> None:
        try:
            option_list = self.query_one("#picker-list", OptionList)
        except Exception:
            return

        option_list.clear_options()
        if self._current_tab == TAB_CONNECTIONS:
            options = build_connections_options(self.connections, self.search_text)
        elif self._current_tab == TAB_DOCKER:
            options = build_docker_options(
                self.connections,
                self._docker_containers,
                self.search_text,
                loading=self._loading_docker,
                status_message=self._docker_status_message,
            )
        else:
            options = []

        for opt in options:
            option_list.add_option(opt)

        self._select_first_selectable()

    def _select_first_selectable(self) -> None:
        try:
            option_list = self.query_one("#picker-list", OptionList)
        except Exception:
            return

        for i in range(option_list.option_count):
            option = option_list.get_option_at_index(i)
            if option and not option.disabled:
                option_list.highlighted = i
                return

    def _update_list(self) -> None:
        self._rebuild_list()
        self._update_shortcuts()

    def _rebuild_cloud_tree(self) -> None:
        try:
            tree = self.query_one("#cloud-tree", Tree)
        except Exception:
            return
        build_cloud_tree(
            tree,
            providers=self._cloud_providers,
            states=self._cloud_states,
            connections=self.connections,
            loading_databases=self._loading_databases,
        )

    def on_key(self, event: Key) -> None:
        if not self._filter_active:
            return

        key = event.key
        if key == "backspace":
            if self.search_text:
                self.search_text = self.search_text[:-1]
                self._update_filter_display()
                self._update_list()
            else:
                self._close_filter()
            event.prevent_default()
            event.stop()
            return

        if event.character and event.character.isprintable():
            self.search_text += event.character
            self._update_filter_display()
            self._update_list()
            event.prevent_default()
            event.stop()

    def action_backspace(self) -> None:
        if not self._filter_active:
            return
        pass

    def action_open_filter(self) -> None:
        self._filter_active = True
        self.search_text = ""
        filter_input = self.query_one("#picker-filter", FilterInput)
        filter_input.show()
        self._update_filter_display()

    def _close_filter(self) -> None:
        self._filter_active = False
        self.search_text = ""
        filter_input = self.query_one("#picker-filter", FilterInput)
        filter_input.hide()
        self._update_list()

    def _update_filter_display(self) -> None:
        filter_input = self.query_one("#picker-filter", FilterInput)
        total = len(self.connections) + len(self._docker_containers)
        if self.search_text:
            match_count = self._count_matches()
            filter_input.set_filter(self.search_text, match_count, total)
        else:
            filter_input.set_filter("", 0, total)

    def _count_matches(self) -> int:
        count = 0
        pattern = self.search_text
        for conn in self.connections:
            matches, _ = fuzzy_match(pattern, conn.name)
            if matches:
                count += 1
        for container in self._docker_containers:
            matches, _ = fuzzy_match(pattern, container.container_name)
            if matches:
                count += 1
        return count

    def action_cancel_or_close_filter(self) -> None:
        if self._filter_active:
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
            container = find_container_by_id(self._docker_containers, container_id)
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
        if not tree_node or not tree_node.data:
            return None
        data = tree_node.data
        if not isinstance(data, CloudNodeData) or not data.option_id:
            return None
        provider_id = data.provider_id
        option_id = data.option_id
        state = self._cloud_states.get(provider_id, ProviderState())
        response = self._cloud_actions.handle(
            CloudActionRequest(provider_id, "select", option_id),
            state=state,
            connections=self.connections,
        )
        config = self._handle_cloud_action_response(provider_id, response)
        if response.action == "connect":
            return config
        return None

    def _handle_cloud_action(self, action: str) -> None:
        if self._current_tab != TAB_CLOUD:
            return
        tree_node = self._get_highlighted_tree_node()
        if not tree_node or not tree_node.data:
            return
        data = tree_node.data
        if not isinstance(data, CloudNodeData) or not data.option_id:
            return
        provider_id = data.provider_id
        state = self._cloud_states.get(provider_id, ProviderState())
        response = self._cloud_actions.handle(
            CloudActionRequest(provider_id, action, data.option_id),
            state=state,
            connections=self.connections,
        )
        self._handle_cloud_action_response(provider_id, response)

    def _handle_cloud_action_response(
        self,
        provider_id: str,
        response: CloudActionResponse,
    ) -> ConnectionConfig | None:
        if response.action == "login":
            self._start_provider_login(provider_id)
            return None
        if response.action == "logout":
            self._start_provider_logout(provider_id)
            return None
        if response.action == "switch_subscription":
            index = int(response.metadata.get("subscription_index", 0))
            self._switch_cloud_subscription(provider_id, index)
            return None
        if response.action in ("connect", "save"):
            return response.config
        return None

    def _switch_cloud_subscription(self, provider_id: str, index: int) -> None:
        adapter = self._cloud_ui_adapters.get(provider_id)
        provider = self._cloud_actions.get_provider(provider_id)
        if adapter is None or provider is None:
            return
        adapter.switch_subscription(self, provider, index)

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
        option_list = self.query_one("#picker-list", OptionList)
        cloud_tree = self.query_one("#cloud-tree", Tree)

        if self._current_tab == TAB_CLOUD:
            option_list.add_class("hidden")
            cloud_tree.add_class("visible")
            self._rebuild_cloud_tree()
        else:
            option_list.remove_class("hidden")
            cloud_tree.remove_class("visible")

    def action_new_connection(self) -> None:
        self.dismiss("__new_connection__")

    def action_refresh(self) -> None:
        from sqlit.domains.connections.discovery.cloud.aws.cache import clear_aws_cache
        from sqlit.domains.connections.discovery.cloud.gcp.cache import clear_gcp_cache
        from sqlit.domains.connections.discovery.cloud_detector import clear_azure_cache

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
            container = find_container_by_id(self._docker_containers, container_id)
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
            self.notify(result.warning)
        if result.saved:
            self.notify(result.message)
        else:
            self.notify(result.message, severity="error")
            return

        self._rebuild_list()
        if hasattr(self.app, "refresh_tree"):
            self.app.refresh_tree()

        if self._current_tab == TAB_DOCKER:
            self._select_option_by_id(option_id)
        elif self._current_tab == TAB_CLOUD:
            self._rebuild_cloud_tree()
        self._update_shortcuts()

    def _select_option_by_id(self, option_id: str) -> None:
        try:
            option_list = self.query_one("#picker-list", OptionList)
            for i in range(option_list.option_count):
                option = option_list.get_option_at_index(i)
                if option and option.id == option_id:
                    option_list.highlighted = i
                    return
        except Exception:
            pass
