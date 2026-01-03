"""Expansion state helpers for explorer tree mixins."""

from __future__ import annotations

from typing import Any

from sqlit.shared.ui.protocols import TreeMixinHost


def get_node_path(host: TreeMixinHost, node: Any) -> str:
    """Get a unique path string for a tree node."""
    parts: list[str] = []
    current = node
    while current and current.parent:
        data = current.data
        if data:
            path_part = host._get_node_path_part(data)
            if path_part:
                parts.append(path_part)
        current = current.parent
    return "/".join(reversed(parts))


def restore_subtree_expansion(host: TreeMixinHost, node: Any) -> None:
    """Recursively expand nodes that should be expanded."""
    for child in node.children:
        if child.data:
            path = get_node_path(host, child)
            if path in host._expanded_paths:
                child.expand()
        restore_subtree_expansion(host, child)


def update_expanded_state(host: TreeMixinHost, node: Any, expanded: bool) -> None:
    """Update expanded state for a single node."""
    path = get_node_path(host, node)
    if not path:
        return
    expanded_paths = getattr(host, "_expanded_paths", set())
    if expanded:
        expanded_paths.add(path)
        host._expanded_paths = expanded_paths
        return
    expanded_paths.discard(path)
    prefix = f"{path}/"
    to_remove = [item for item in expanded_paths if item.startswith(prefix)]
    for item in to_remove:
        expanded_paths.discard(item)
    host._expanded_paths = expanded_paths


def persist_expanded_state(host: TreeMixinHost) -> None:
    """Persist expanded state to settings."""
    expanded = sorted(getattr(host, "_expanded_paths", set()))
    settings = host.services.settings_store.load_all()
    settings["expanded_nodes"] = expanded
    host.services.settings_store.save_all(settings)


def save_expanded_state(host: TreeMixinHost) -> None:
    """Save which nodes are expanded (full tree scan)."""
    expanded: list[str] = []

    def collect_expanded(node: Any) -> None:
        if node.is_expanded and node.data:
            path = get_node_path(host, node)
            if path:
                expanded.append(path)
        for child in node.children:
            collect_expanded(child)

    collect_expanded(host.object_tree.root)

    host._expanded_paths = set(expanded)
    settings = host.services.settings_store.load_all()
    settings["expanded_nodes"] = expanded
    host.services.settings_store.save_all(settings)
