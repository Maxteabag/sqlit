"""Async loading helpers for explorer tree mixins."""

from __future__ import annotations

from typing import Any

from rich.markup import escape as escape_markup

from sqlit.domains.explorer.domain.tree_nodes import (
    ColumnNode,
    FolderNode,
    IndexNode,
    LoadingNode,
    ProcedureNode,
    SequenceNode,
    TableNode,
    TriggerNode,
    ViewNode,
)
from sqlit.shared.ui.protocols import TreeMixinHost

from . import expansion_state, schema_render


def ensure_loading_nodes(host: TreeMixinHost) -> set[str]:
    loading_nodes = getattr(host, "_loading_nodes", None)
    if loading_nodes is None:
        loading_nodes = set()
        host._loading_nodes = loading_nodes
    return loading_nodes


def add_loading_placeholder(host: TreeMixinHost, node: Any) -> None:
    loading_node = node.add_leaf("[dim italic]Loading...[/]")
    loading_node.data = LoadingNode()


def remove_loading_placeholders(host: TreeMixinHost, node: Any) -> None:
    for child in list(node.children):
        if host._get_node_kind(child) == "loading":
            child.remove()


def clear_loading_state(host: TreeMixinHost, node: Any) -> None:
    node_path = expansion_state.get_node_path(host, node)
    loading_nodes = ensure_loading_nodes(host)
    loading_nodes.discard(node_path)
    remove_loading_placeholders(host, node)


def load_columns_async(host: TreeMixinHost, node: Any, data: TableNode | ViewNode) -> None:
    """Spawn worker to load columns for a table/view."""
    db_name = data.database
    schema_name = data.schema
    obj_name = data.name

    def work() -> None:
        """Run in worker thread."""
        try:
            schema_service = host._get_schema_service()
            if not schema_service:
                columns = []
            else:
                columns = schema_service.list_columns(db_name, schema_name, obj_name)

            host.call_from_thread(
                on_columns_loaded, host, node, db_name, schema_name, obj_name, columns
            )
        except Exception as error:
            host.call_from_thread(on_tree_load_error, host, node, f"Error loading columns: {error}")

    host.run_worker(work, name=f"load-columns-{obj_name}", thread=True, exclusive=False)


def on_columns_loaded(
    host: TreeMixinHost,
    node: Any,
    db_name: str | None,
    schema_name: str,
    obj_name: str,
    columns: list[Any],
) -> None:
    """Handle column load completion on main thread."""
    clear_loading_state(host, node)

    if not columns:
        empty_child = node.add_leaf("[dim](Empty)[/]")
        empty_child.data = LoadingNode()
        return

    for col in columns:
        col_name = escape_markup(col.name)
        col_type = escape_markup(col.data_type)
        child = node.add_leaf(f"[dim]{col_name}[/] [italic dim]{col_type}[/]")
        child.data = ColumnNode(database=db_name, schema=schema_name, table=obj_name, name=col.name)


def load_folder_async(host: TreeMixinHost, node: Any, data: FolderNode) -> None:
    """Spawn worker to load folder contents (tables/views/indexes/triggers/sequences/procedures)."""
    folder_type = data.folder_type
    db_name = data.database

    def work() -> None:
        """Run in worker thread."""
        try:
            schema_service = host._get_schema_service()
            if not schema_service:
                items = []
            else:
                items = schema_service.list_folder_items(folder_type, db_name)

            host.call_from_thread(on_folder_loaded, host, node, db_name, folder_type, items)
        except Exception as error:
            host.call_from_thread(on_tree_load_error, host, node, f"Error loading: {error}")

    host.run_worker(work, name=f"load-folder-{folder_type}", thread=True, exclusive=False)


def on_folder_loaded(
    host: TreeMixinHost, node: Any, db_name: str | None, folder_type: str, items: list[Any]
) -> None:
    """Handle folder load completion on main thread."""
    clear_loading_state(host, node)

    if not host._session:
        return

    provider = host._session.provider
    if not items:
        empty_child = node.add_leaf("[dim](Empty)[/]")
        empty_child.data = LoadingNode()
        return

    if folder_type in ("tables", "views"):
        schema_render.add_schema_grouped_items(
            host, node, db_name, folder_type, items, provider.capabilities.default_schema
        )
        return

    for item in items:
        if item[0] == "procedure":
            child = node.add_leaf(escape_markup(item[2]))
            child.data = ProcedureNode(database=db_name, name=item[2])
        elif item[0] == "index":
            display = f"{escape_markup(item[1])} [dim]({escape_markup(item[2])})[/]"
            child = node.add_leaf(display)
            child.data = IndexNode(database=db_name, name=item[1], table_name=item[2])
        elif item[0] == "trigger":
            display = f"{escape_markup(item[1])} [dim]({escape_markup(item[2])})[/]"
            child = node.add_leaf(display)
            child.data = TriggerNode(database=db_name, name=item[1], table_name=item[2])
        elif item[0] == "sequence":
            child = node.add_leaf(escape_markup(item[1]))
            child.data = SequenceNode(database=db_name, name=item[1])


def on_tree_load_error(host: TreeMixinHost, node: Any, error_message: str) -> None:
    """Handle tree load error on main thread."""
    clear_loading_state(host, node)
    host.notify(escape_markup(error_message), severity="error")
