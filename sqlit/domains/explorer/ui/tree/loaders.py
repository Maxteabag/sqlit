"""Async loading helpers for explorer tree mixins."""

from __future__ import annotations

from typing import Any

from rich.markup import escape as escape_markup

from sqlit.domains.explorer.domain.tree_nodes import (
    ColumnNode,
    DatabaseNode,
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

MIN_TIMER_DELAY_S = 0.001


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

    async def work_async() -> None:
        import asyncio

        try:
            columns = []
            runtime = getattr(host.services, "runtime", None)
            use_worker = bool(getattr(runtime, "process_worker", False)) and not bool(
                getattr(getattr(runtime, "mock", None), "enabled", False)
            )
            if use_worker:
                try:
                    from sqlit.domains.process_worker.app.support import supports_process_worker
                except Exception:
                    pass
                else:
                    provider = getattr(host, "current_provider", None)
                    use_worker = supports_process_worker(provider)
            if use_worker and hasattr(host, "_get_process_worker_client_async"):
                client = await host._get_process_worker_client_async()  # type: ignore[attr-defined]
            else:
                client = None

            if client is not None and hasattr(client, "list_columns") and host.current_config is not None:
                outcome = await asyncio.to_thread(
                    client.list_columns,
                    config=host.current_config,
                    database=db_name,
                    schema=schema_name,
                    name=obj_name,
                )
                if getattr(outcome, "error", None):
                    raise RuntimeError(outcome.error)
                if getattr(outcome, "cancelled", False):
                    return
                columns = outcome.columns or []
            else:
                schema_service = host._get_schema_service()
                if schema_service:
                    columns = await asyncio.to_thread(
                        schema_service.list_columns,
                        db_name,
                        schema_name,
                        obj_name,
                    )

            host.set_timer(
                MIN_TIMER_DELAY_S,
                lambda: on_columns_loaded(host, node, db_name, schema_name, obj_name, columns),
            )
        except Exception as error:
            error_message = f"Error loading columns: {error}"
            host.set_timer(
                MIN_TIMER_DELAY_S,
                lambda: on_tree_load_error(host, node, error_message),
            )

    host.run_worker(work_async(), name=f"load-columns-{obj_name}", exclusive=False)


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

    batch_size = 50
    total = len(columns)
    idx = 0

    def render_batch() -> None:
        nonlocal idx
        if idx >= total:
            return
        end = min(idx + batch_size, total)
        for col in columns[idx:end]:
            col_name = escape_markup(col.name)
            col_type = escape_markup(col.data_type)
            child = node.add_leaf(f"[dim]{col_name}[/] [italic dim]{col_type}[/]")
            child.data = ColumnNode(database=db_name, schema=schema_name, table=obj_name, name=col.name)
        idx = end
        if idx < total:
            host.set_timer(MIN_TIMER_DELAY_S, render_batch)

    render_batch()


def load_folder_async(host: TreeMixinHost, node: Any, data: FolderNode) -> None:
    """Spawn worker to load folder contents (tables/views/indexes/triggers/sequences/procedures)."""
    folder_type = data.folder_type
    db_name = data.database

    async def work_async() -> None:
        import asyncio

        try:
            items: list[Any] = []
            runtime = getattr(host.services, "runtime", None)
            use_worker = bool(getattr(runtime, "process_worker", False)) and not bool(
                getattr(getattr(runtime, "mock", None), "enabled", False)
            )
            if use_worker:
                try:
                    from sqlit.domains.process_worker.app.support import supports_process_worker
                except Exception:
                    pass
                else:
                    provider = getattr(host, "current_provider", None)
                    use_worker = supports_process_worker(provider)
            client = None
            if use_worker and hasattr(host, "_get_process_worker_client_async"):
                client = await host._get_process_worker_client_async()  # type: ignore[attr-defined]

            if client is not None and hasattr(client, "list_folder_items") and host.current_config is not None:
                outcome = await asyncio.to_thread(
                    client.list_folder_items,
                    config=host.current_config,
                    database=db_name,
                    folder_type=folder_type,
                )
                if getattr(outcome, "cancelled", False):
                    return
                error = getattr(outcome, "error", None)
                if error:
                    raise RuntimeError(error)
                items = outcome.items or []
            else:
                schema_service = host._get_schema_service()
                if schema_service:
                    items = await asyncio.to_thread(
                        schema_service.list_folder_items,
                        folder_type,
                        db_name,
                    )

            host.set_timer(
                MIN_TIMER_DELAY_S,
                lambda: on_folder_loaded(host, node, db_name, folder_type, items),
            )
        except Exception as error:
            error_message = f"Error loading: {error}"
            host.set_timer(
                MIN_TIMER_DELAY_S,
                lambda: on_tree_load_error(host, node, error_message),
            )

    host.run_worker(work_async(), name=f"load-folder-{folder_type}", exclusive=False)


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

    if folder_type == "databases":
        active_db = None
        if hasattr(host, "_get_effective_database"):
            active_db = host._get_effective_database()
        from . import builder as tree_builder

        for db in items:
            if active_db and str(db).lower() == str(active_db).lower():
                db_label = f"[#4ADE80]* {escape_markup(str(db))}[/]"
            else:
                db_label = escape_markup(str(db))
            db_node = node.add(db_label)
            db_node.data = DatabaseNode(name=str(db))
            db_node.allow_expand = True
            tree_builder.add_database_object_nodes(host, db_node, str(db))

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
