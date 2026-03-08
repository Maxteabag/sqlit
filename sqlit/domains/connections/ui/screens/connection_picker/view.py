"""View helpers for the connection picker screen."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.widgets import OptionList, Tree
from textual.widgets.option_list import Option
from textual.widgets.tree import TreeNode

from sqlit.domains.connections.app.cloud_actions import CloudActionService
from sqlit.domains.connections.discovery.cloud import ProviderState
from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.ui.screens.connection_picker.constants import (
    TAB_CLOUD,
    TAB_CONNECTIONS,
    TAB_DOCKER,
)
from sqlit.domains.connections.ui.screens.connection_picker.shortcuts import build_picker_shortcuts
from sqlit.domains.connections.ui.screens.connection_picker.tabs import (
    build_cloud_tree,
    build_connections_options,
    build_docker_options,
)
from sqlit.shared.ui.widgets import Dialog, FilterInput

if TYPE_CHECKING:
    from sqlit.domains.connections.discovery.docker_detector import DetectedContainer
    from sqlit.domains.connections.ui.screens.connection_picker.screen import ConnectionPickerScreen


class PickerView:
    """Widget helpers for the connection picker UI."""

    def __init__(self, screen: ConnectionPickerScreen) -> None:
        self._screen = screen

    def _get(self, selector: str, widget_type: type[Any]) -> Any | None:
        try:
            return self._screen.query_one(selector, widget_type)
        except Exception:
            return None

    def _dialog(self) -> Dialog | None:
        return self._get("#picker-dialog", Dialog)

    def _option_list(self) -> OptionList | None:
        return self._get("#picker-list", OptionList)

    def _cloud_tree(self) -> Tree | None:
        return self._get("#cloud-tree", Tree)

    def _filter_input(self) -> FilterInput | None:
        return self._get("#picker-filter", FilterInput)

    def get_highlighted_option(self) -> Option | None:
        option_list = self._option_list()
        if option_list is None:
            return None
        highlighted = option_list.highlighted
        if highlighted is None:
            return None
        return option_list.get_option_at_index(highlighted)

    def get_highlighted_tree_node(self) -> TreeNode | None:
        tree = self._cloud_tree()
        if tree is None:
            return None
        return tree.cursor_node

    def update_dialog_title(self, current_tab: str) -> None:
        dialog = self._dialog()
        if dialog is None:
            return
        if current_tab == TAB_CONNECTIONS:
            dialog.border_title = "[bold]Connections[/] | [dim]Docker[/] | [dim]Cloud[/]  [dim]<tab>[/]"
        elif current_tab == TAB_DOCKER:
            dialog.border_title = "[dim]Connections[/] | [bold]Docker[/] | [dim]Cloud[/]  [dim]<tab>[/]"
        else:
            dialog.border_title = "[dim]Connections[/] | [dim]Docker[/] | [bold]Cloud[/]  [dim]<tab>[/]"

    def update_shortcuts(
        self,
        *,
        current_tab: str,
        providers: list[Any],
        cloud_states: dict[str, ProviderState],
        cloud_actions: CloudActionService,
        connections: list[ConnectionConfig],
        docker_containers: list[DetectedContainer],
    ) -> None:
        dialog = self._dialog()
        if dialog is None:
            return
        option = self.get_highlighted_option()
        tree_node = self.get_highlighted_tree_node()
        shortcuts = build_picker_shortcuts(
            current_tab=current_tab,
            option=option,
            tree_node=tree_node,
            providers=providers,
            cloud_states=cloud_states,
            cloud_actions=cloud_actions,
            connections=connections,
            docker_containers=docker_containers,
        )
        dialog.border_subtitle = " ".join(f"{label}: <{key}>" for label, key in shortcuts)

    def rebuild_list(
        self,
        *,
        current_tab: str,
        connections: list[ConnectionConfig],
        search_text: str,
        docker_containers: list[DetectedContainer],
        loading_docker: bool,
        docker_status_message: str | None,
    ) -> None:
        option_list = self._option_list()
        if option_list is None:
            return

        previous_id: str | None = None
        if option_list.highlighted is not None:
            try:
                prev_option = option_list.get_option_at_index(option_list.highlighted)
                if prev_option:
                    previous_id = prev_option.id
            except Exception:
                pass

        option_list.clear_options()
        if current_tab == TAB_CONNECTIONS:
            options = build_connections_options(connections, search_text)
        elif current_tab == TAB_DOCKER:
            options = build_docker_options(
                connections,
                docker_containers,
                search_text,
                loading=loading_docker,
                status_message=docker_status_message,
            )
        else:
            options = []

        for opt in options:
            option_list.add_option(opt)

        self.restore_selection(previous_id)

    def restore_selection(self, previous_id: str | None) -> None:
        option_list = self._option_list()
        if option_list is None:
            return

        if previous_id:
            for i in range(option_list.option_count):
                option = option_list.get_option_at_index(i)
                if option and option.id == previous_id and not option.disabled:
                    option_list.highlighted = i
                    return

        self.select_first_selectable()

    def select_first_selectable(self) -> None:
        option_list = self._option_list()
        if option_list is None:
            return
        for i in range(option_list.option_count):
            option = option_list.get_option_at_index(i)
            if option and not option.disabled:
                option_list.highlighted = i
                return

    def rebuild_cloud_tree(
        self,
        *,
        providers: list[Any],
        states: dict[str, ProviderState],
        connections: list[ConnectionConfig],
        loading_databases: set[str],
    ) -> None:
        tree = self._cloud_tree()
        if tree is None:
            return
        build_cloud_tree(
            tree,
            providers=providers,
            states=states,
            connections=connections,
            loading_databases=loading_databases,
        )

    def set_tab_visibility(
        self,
        *,
        current_tab: str,
        providers: list[Any],
        states: dict[str, ProviderState],
        connections: list[ConnectionConfig],
        loading_databases: set[str],
    ) -> None:
        option_list = self._option_list()
        cloud_tree = self._cloud_tree()
        if option_list is None or cloud_tree is None:
            return
        if current_tab == TAB_CLOUD:
            option_list.add_class("hidden")
            cloud_tree.add_class("visible")
            self.rebuild_cloud_tree(
                providers=providers,
                states=states,
                connections=connections,
                loading_databases=loading_databases,
            )
        else:
            option_list.remove_class("hidden")
            cloud_tree.remove_class("visible")

    def show_filter(self) -> None:
        filter_input = self._filter_input()
        if filter_input is not None:
            filter_input.show()

    def hide_filter(self) -> None:
        filter_input = self._filter_input()
        if filter_input is not None:
            filter_input.hide()

    def set_filter_display(self, text: str, match_count: int, total: int) -> None:
        filter_input = self._filter_input()
        if filter_input is not None:
            filter_input.set_filter(text, match_count, total)

    def select_option_by_id(self, option_id: str) -> None:
        option_list = self._option_list()
        if option_list is None:
            return
        for i in range(option_list.option_count):
            option = option_list.get_option_at_index(i)
            if option and option.id == option_id:
                option_list.highlighted = i
                return
