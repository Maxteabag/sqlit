"""Cloud tab helpers for the connection picker."""

from __future__ import annotations

from typing import Any

from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from sqlit.domains.connections.discovery.cloud import ProviderState, ProviderStatus
from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.ui.screens.connection_picker.cloud_nodes import CloudNodeData
from sqlit.domains.connections.ui.screens.connection_picker.cloud_providers import (
    get_cloud_ui_adapter,
)


def build_cloud_tree(
    tree: Tree,
    *,
    providers: list[Any],
    states: dict[str, ProviderState],
    connections: list[ConnectionConfig],
    loading_databases: set[str],
) -> None:
    tree.clear()
    tree.root.expand()

    for provider in providers:
        state = states.get(provider.id, ProviderState())
        _add_provider_node(tree.root, provider, state, connections, loading_databases)


def _add_provider_node(
    parent: TreeNode,
    provider: Any,
    state: ProviderState,
    connections: list[ConnectionConfig],
    loading_databases: set[str],
) -> None:
    adapter = get_cloud_ui_adapter(provider.id)
    provider_node = parent.add(f"[bold]{provider.name}[/]", expand=True)
    provider_node.data = CloudNodeData(provider_id=provider.id)

    if state.loading:
        provider_node.add_leaf("[dim italic]Loading...[/]")
        return

    if state.status == ProviderStatus.CLI_NOT_INSTALLED:
        provider_node.add_leaf(f"[dim]({provider.name.lower()} CLI not installed)[/]")
        return

    if state.status == ProviderStatus.NOT_LOGGED_IN:
        login_node = provider_node.add_leaf(f"Login to {provider.name}...")
        if adapter is not None:
            login_node.data = CloudNodeData(
                provider_id=provider.id,
                option_id=adapter.login_option_id(provider),
            )
        return

    if state.status == ProviderStatus.ERROR:
        provider_node.add_leaf(f"[red]Warning: {provider.name} error[/]")
        if state.error:
            provider_node.add_leaf(f"[dim]{state.error}[/]")
        return

    if state.status == ProviderStatus.NOT_SUPPORTED:
        provider_node.add_leaf("[dim](coming soon)[/]")
        return

    if state.account is None:
        provider_node.add_leaf("[dim](no account available)[/]")
        return

    account_display = state.account.username
    if len(account_display) > 40:
        account_display = account_display[:37] + "..."
    account_node = provider_node.add(f"Account: {account_display}", expand=True)
    if adapter is not None:
        account_node.data = CloudNodeData(
            provider_id=provider.id,
            option_id=adapter.account_option_id(provider),
        )
        adapter.build_resources(account_node, provider, state, connections, loading_databases)
