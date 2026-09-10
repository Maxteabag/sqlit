"""Persistent explorer layout selection."""

from __future__ import annotations

from typing import Any

from .router import register_command_handler


def apply_explorer_layout(app: Any, layout: str) -> None:
    if layout not in {"schema", "type"}:
        raise ValueError("Explorer layout must be 'schema' or 'type'")
    if getattr(app, "_tree_filter_visible", False):
        app.action_tree_filter_close()
    store = app.services.settings_store
    settings = store.load_all()
    previous = settings.get("explorer_hierarchy", "type")
    if previous not in {"schema", "type"}:
        previous = "type"
    if previous != layout:
        # Keep both layouts' expansion paths, since their parent order differs.
        raw_paths = settings.get("explorer_expanded_by_hierarchy", {})
        paths = dict(raw_paths) if isinstance(raw_paths, dict) else {}
        paths[previous] = sorted(app._expanded_paths)
        restored = paths.get(layout, [])
        app._expanded_paths = {path for path in restored if isinstance(path, str)} if isinstance(restored, list) else set()
        settings["explorer_expanded_by_hierarchy"] = paths
        settings["expanded_nodes"] = sorted(app._expanded_paths)
    settings["explorer_hierarchy"] = layout
    store.save_all(settings)
    if previous != layout:
        # Old paths cannot identify a cursor after the hierarchy is inverted.
        # Start at its connection; same-layout refresh still restores exact paths.
        node = app.object_tree.cursor_node
        while node is not None and app._get_node_kind(node) != "connection":
            node = node.parent
        if node is not None:
            app.object_tree.move_cursor(node)
        app._loading_nodes.clear()
        app.refresh_tree()
    provider = app.current_provider
    label = "schema" if layout == "schema" else "object type"
    message = f"Explorer grouped by {label}"
    if layout == "schema" and provider and not provider.capabilities.supports_schema_grouping:
        message = "Schema layout saved; this connection keeps its existing layout"
    app.notify(message)


def show_explorer_layout(app: Any) -> None:
    from sqlit.domains.shell.ui.screens.explorer_layout import ExplorerLayoutScreen

    current = app.services.settings_store.get("explorer_hierarchy", "type")
    provider = app.current_provider
    supported = provider.capabilities.supports_schema_grouping if provider else None

    def selected(layout: str | None) -> None:
        if layout:
            apply_explorer_layout(app, layout)

    app.push_screen(ExplorerLayoutScreen(current, supported=supported), selected)


def _handle_explorer_command(app: Any, cmd: str, args: list[str]) -> bool:
    if cmd != "explorer":
        return False
    if not args:
        show_explorer_layout(app)
    elif len(args) == 1 and args[0].lower() in {"schema", "type"}:
        apply_explorer_layout(app, args[0].lower())
    else:
        app.notify("Usage: :explorer [schema|type]", severity="warning")
    return True


register_command_handler(_handle_explorer_command)
