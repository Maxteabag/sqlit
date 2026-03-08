"""Shortcut rendering logic for the connection picker."""

from __future__ import annotations

from typing import Any

from textual.widgets.option_list import Option
from textual.widgets.tree import TreeNode

from sqlit.domains.connections.app.cloud_actions import CloudActionRequest, CloudActionService
from sqlit.domains.connections.app.save_connection import is_config_saved
from sqlit.domains.connections.discovery.cloud import ProviderState
from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.ui.screens.connection_picker.cloud_nodes import CloudNodeData
from sqlit.domains.connections.ui.screens.connection_picker.constants import (
    TAB_CLOUD,
    TAB_CONNECTIONS,
    TAB_DOCKER,
)
from sqlit.domains.connections.ui.screens.connection_picker.tabs.docker import (
    DOCKER_PREFIX,
    find_container_by_id,
    is_container_saved,
)


def build_picker_shortcuts(
    *,
    current_tab: str,
    option: Option | None,
    tree_node: TreeNode | None,
    providers: list[Any],
    cloud_states: dict[str, ProviderState],
    cloud_actions: CloudActionService,
    connections: list[ConnectionConfig],
    docker_containers: list[Any],
) -> list[tuple[str, str]]:
    if current_tab == TAB_CLOUD:
        return _build_cloud_shortcuts(
            tree_node=tree_node,
            providers=providers,
            cloud_states=cloud_states,
            cloud_actions=cloud_actions,
            connections=connections,
        )

    return _build_list_shortcuts(
        current_tab=current_tab,
        option=option,
        providers=providers,
        cloud_states=cloud_states,
        cloud_actions=cloud_actions,
        connections=connections,
        docker_containers=docker_containers,
    )


def _build_list_shortcuts(
    *,
    current_tab: str,
    option: Option | None,
    providers: list[Any],
    cloud_states: dict[str, ProviderState],
    cloud_actions: CloudActionService,
    connections: list[ConnectionConfig],
    docker_containers: list[Any],
) -> list[tuple[str, str]]:
    show_save = False
    is_connectable = False
    provider_shortcuts: list[tuple[str, str]] = []

    if option:
        option_id = str(option.id) if option.id else ""

        for provider in providers:
            if provider.is_my_option(option_id):
                state = cloud_states.get(provider.id, ProviderState())
                provider_shortcuts = provider.get_shortcuts(option_id, state)
                result = cloud_actions.handle(
                    CloudActionRequest(provider.id, "check_save", option_id),
                    state=state,
                    connections=connections,
                )
                if result.config is not None:
                    show_save = not is_config_saved(connections, result.config)
                break

        if not provider_shortcuts and option_id.startswith(DOCKER_PREFIX):
            is_connectable = True
            container_id = option_id[len(DOCKER_PREFIX):]
            container = find_container_by_id(docker_containers, container_id)
            if container and not is_container_saved(connections, container):
                show_save = True

        if current_tab == TAB_CONNECTIONS and option_id:
            is_connectable = True

    shortcuts = provider_shortcuts
    if not shortcuts:
        action_label = "Connect" if is_connectable else "Select"
        shortcuts = [(action_label, "enter")]
        if show_save:
            shortcuts.append(("Save", "s"))
        if current_tab == TAB_CONNECTIONS:
            shortcuts.append(("New", "n"))

    if current_tab in (TAB_DOCKER, TAB_CLOUD):
        shortcuts.append(("Refresh", "f"))

    return shortcuts


def _build_cloud_shortcuts(
    *,
    tree_node: TreeNode | None,
    providers: list[Any],
    cloud_states: dict[str, ProviderState],
    cloud_actions: CloudActionService,
    connections: list[ConnectionConfig],
) -> list[tuple[str, str]]:
    show_save = False
    is_connectable = False
    is_expandable = False
    provider_shortcuts: list[tuple[str, str]] = []

    if tree_node and tree_node.data:
        data = tree_node.data
        if isinstance(data, CloudNodeData):
            provider_id = data.provider_id
            option_id = data.option_id
            if tree_node.allow_expand and tree_node.children:
                is_expandable = True

            provider = cloud_actions.get_provider(provider_id)
            state = cloud_states.get(provider_id, ProviderState())
            if provider and option_id:
                provider_shortcuts = provider.get_shortcuts(option_id, state)
                result = cloud_actions.handle(
                    CloudActionRequest(provider_id, "check_save", option_id),
                    state=state,
                    connections=connections,
                )
                if result.config is not None:
                    is_connectable = True
                    show_save = not is_config_saved(connections, result.config)

    shortcuts = provider_shortcuts
    if not shortcuts:
        if is_connectable:
            action_label = "Connect"
        elif is_expandable:
            action_label = "Expand"
        else:
            action_label = "Select"
        shortcuts = [(action_label, "enter")]
        if show_save:
            shortcuts.append(("Save", "s"))

    shortcuts.append(("Refresh", "f"))
    return shortcuts
