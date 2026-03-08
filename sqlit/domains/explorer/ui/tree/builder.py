"""Tree construction helpers for explorer tree mixins."""

from __future__ import annotations

from typing import Any, Callable
from contextlib import nullcontext

from rich.markup import escape as escape_markup

from sqlit.domains.connections.providers.metadata import get_connection_display_info
from sqlit.domains.explorer.domain.tree_nodes import ConnectionFolderNode, ConnectionNode, FolderNode
from sqlit.domains.explorer.ui.tree.expansion_state import (
    find_node_by_path,
    get_node_path,
    restore_subtree_expansion_with_paths,
)
from sqlit.shared.ui.protocols import TreeMixinHost

MIN_TIMER_DELAY_S = 0.001
POPULATE_CONNECTED_DEFER_S = 0.15
MAX_SYNC_CONNECTIONS = 50


def _sort_connections_for_display(connections: list[Any]) -> list[Any]:
    grouped: dict[str, list[Any]] = {}
    order: list[str] = []
    for conn in connections:
        folder_path = getattr(conn, "folder_path", "") or ""
        if folder_path not in grouped:
            grouped[folder_path] = []
            order.append(folder_path)
        grouped[folder_path].append(conn)

    ordered: list[Any] = []
    for folder_path in order:
        ordered.extend(grouped[folder_path])
    return ordered


def _build_connection_folders(host: TreeMixinHost, connections: list[Any]) -> None:
    for conn in connections:
        folder_parts = _split_folder_path(getattr(conn, "folder_path", ""))
        if folder_parts:
            _ensure_connection_folder_path(host, folder_parts)


def _split_folder_path(path: str | None) -> list[str]:
    if not path:
        return []
    return [part for part in str(path).split("/") if part]


def _find_connection_folder_child(host: TreeMixinHost, parent: Any, name: str) -> Any | None:
    for child in parent.children:
        if host._get_node_kind(child) != "connection_folder":
            continue
        data = getattr(child, "data", None)
        if getattr(data, "name", None) == name:
            return child
    return None


def _ensure_connection_folder_path(host: TreeMixinHost, folder_parts: list[str]) -> Any:
    parent = host.object_tree.root
    for part in folder_parts:
        node = _find_connection_folder_child(host, parent, part)
        if node is None:
            node = parent.add(f"📁 {escape_markup(part)}")
            node.data = ConnectionFolderNode(name=part)
            node.allow_expand = True
        parent = node
    return parent


def _add_connection_node(
    host: TreeMixinHost,
    config: Any,
    *,
    is_connected: bool,
    is_connecting: bool,
    spinner: str | None,
    skip_folder: bool = False,
) -> Any:
    if is_connected:
        label = host._format_connection_label(config, "connected")
    elif is_connecting:
        label = host._format_connection_label(config, "connecting", spinner=spinner)
    else:
        label = host._format_connection_label(config, "idle")

    if skip_folder:
        parent = host.object_tree.root
    else:
        folder_parts = _split_folder_path(getattr(config, "folder_path", ""))
        parent = _ensure_connection_folder_path(host, folder_parts)

    node = parent.add(label)
    node.data = ConnectionNode(config=config)
    node.allow_expand = is_connected
    return node


def _find_connection_node(host: TreeMixinHost, config: Any) -> Any | None:
    stack = [host.object_tree.root]
    while stack:
        node = stack.pop()
        for child in node.children:
            if host._get_node_kind(child) == "connection":
                data = getattr(child, "data", None)
                node_config = getattr(data, "config", None)
                if node_config and node_config.name == config.name:
                    return child
            stack.append(child)
    return None


def _find_connection_node_by_name(host: TreeMixinHost, name: str) -> Any | None:
    stack = [host.object_tree.root]
    while stack:
        node = stack.pop()
        for child in node.children:
            if host._get_node_kind(child) == "connection":
                data = getattr(child, "data", None)
                node_config = getattr(data, "config", None)
                if node_config and node_config.name == name:
                    return child
            stack.append(child)
    return None


def _expand_ancestors(host: TreeMixinHost, node: Any) -> None:
    expander = getattr(host, "_expand_ancestors", None)
    if callable(expander):
        expander(node)
        return
    ancestors: list[Any] = []
    current = getattr(node, "parent", None)
    while current and current != host.object_tree.root:
        ancestors.append(current)
        current = getattr(current, "parent", None)
    for ancestor in reversed(ancestors):
        try:
            ancestor.expand()
        except Exception:
            pass


def _restore_cursor(
    host: TreeMixinHost,
    *,
    cursor_path: str,
    cursor_connection_name: str,
) -> None:
    if not cursor_path and not cursor_connection_name:
        _clear_pending_cursor(host)
        return
    node = None
    if cursor_path:
        node = find_node_by_path(host, host.object_tree.root, cursor_path)
    if node is None and cursor_connection_name:
        node = _find_connection_node_by_name(host, cursor_connection_name)
    if node is None:
        _set_pending_cursor(host, cursor_path, cursor_connection_name)
        return
    _clear_pending_cursor(host)
    _expand_ancestors(host, node)

    def apply_cursor() -> None:
        try:
            host.object_tree.move_cursor(node)
        except Exception:
            pass

    call_after_refresh = getattr(host, "call_after_refresh", None)
    if callable(call_after_refresh):
        call_after_refresh(apply_cursor)
        return

    set_timer = getattr(host, "set_timer", None)
    if callable(set_timer):
        set_timer(MIN_TIMER_DELAY_S, apply_cursor)
    else:
        apply_cursor()


def _set_pending_cursor(host: TreeMixinHost, cursor_path: str, cursor_connection_name: str) -> None:
    if not cursor_path and not cursor_connection_name:
        return
    setattr(host, "_pending_tree_cursor_path", cursor_path)
    setattr(host, "_pending_tree_cursor_connection", cursor_connection_name)


def _clear_pending_cursor(host: TreeMixinHost) -> None:
    if hasattr(host, "_pending_tree_cursor_path"):
        setattr(host, "_pending_tree_cursor_path", "")
    if hasattr(host, "_pending_tree_cursor_connection"):
        setattr(host, "_pending_tree_cursor_connection", "")


def restore_pending_cursor(host: TreeMixinHost) -> None:
    cursor_path = getattr(host, "_pending_tree_cursor_path", "")
    cursor_connection_name = getattr(host, "_pending_tree_cursor_connection", "")
    if not cursor_path and not cursor_connection_name:
        return
    _restore_cursor(
        host,
        cursor_path=cursor_path,
        cursor_connection_name=cursor_connection_name,
    )


def _batch_updates(host: TreeMixinHost):
    batch = getattr(host, "batch_update", None)
    if callable(batch):
        return batch()
    return nullcontext()


def _get_connection_folder_path(host: TreeMixinHost, node: Any) -> str:
    parts: list[str] = []
    current = getattr(node, "parent", None)
    while current and current != host.object_tree.root:
        if host._get_node_kind(current) == "connection_folder":
            data = getattr(current, "data", None)
            name = getattr(data, "name", None)
            if name:
                parts.append(str(name))
        current = getattr(current, "parent", None)
    return "/".join(reversed(parts))


def refresh_tree_incremental(
    host: TreeMixinHost,
    *,
    on_done: Callable[[], None] | None = None,
) -> None:
    """Refresh the explorer tree without clearing it to reduce flicker."""
    token = object()
    setattr(host, "_tree_refresh_token", token)

    cursor_path = ""
    cursor_connection_name = ""
    cursor = host.object_tree.cursor_node
    if cursor is not None and cursor.data:
        cursor_path = get_node_path(host, cursor)
        if host._get_node_kind(cursor) == "connection":
            cursor_config = getattr(cursor.data, "config", None)
            if cursor_config and cursor_config.name:
                cursor_connection_name = cursor_config.name

    connecting_config = getattr(host, "_connecting_config", None)
    connecting_name = connecting_config.name if connecting_config else None
    connecting_spinner = host._connect_spinner_frame() if connecting_config else None

    direct_config = getattr(host, "_direct_connection_config", None)
    startup_config = getattr(host, "_startup_connect_config", None)
    exclusive_connection = getattr(host, "_exclusive_connection", False)
    direct_active = (
        direct_config is not None
        and host.current_config is not None
        and direct_config.name == host.current_config.name
    )
    startup_pending = startup_config is not None and not any(
        c.name == startup_config.name for c in host.connections
    )
    exclusive_active = exclusive_connection and startup_config is not None
    if direct_active and host.current_config is not None:
        connections = [host.current_config]
    elif exclusive_active:
        connections = [startup_config]
    elif startup_pending:
        connections = [startup_config]
    else:
        connections = list(host.connections)
    if connecting_config and not any(c.name == connecting_config.name for c in connections):
        connections = connections + [connecting_config]

    connections = _sort_connections_for_display(connections)

    expanded_snapshot = set(getattr(host, "_expanded_paths", set()))

    with _batch_updates(host):
        if not exclusive_active:
            _build_connection_folders(host, connections)

        desired_by_parent: dict[Any, list[Any]] = {}

        # Collect existing connection nodes by name.
        existing_nodes: dict[str, Any] = {}
        stack = [host.object_tree.root]
        while stack:
            node = stack.pop()
            for child in node.children:
                if host._get_node_kind(child) == "connection":
                    data = getattr(child, "data", None)
                    node_config = getattr(data, "config", None)
                    if node_config and node_config.name:
                        existing_nodes[node_config.name] = child
                stack.append(child)

        desired_names = {c.name for c in connections if c is not None}

        # Remove stale nodes.
        for name, node in list(existing_nodes.items()):
            if name not in desired_names:
                try:
                    node.remove()
                except Exception:
                    pass
                existing_nodes.pop(name, None)

        # Add/update nodes.
        for conn in connections:
            if conn is None:
                continue
            is_connected = host.current_config is not None and conn.name == host.current_config.name
            is_connecting = connecting_name == conn.name and not is_connected
            skip_folder = exclusive_active
            if skip_folder:
                parent = host.object_tree.root
            else:
                folder_parts = _split_folder_path(getattr(conn, "folder_path", ""))
                parent = _ensure_connection_folder_path(host, folder_parts)
            desired_by_parent.setdefault(parent, []).append(conn)

            node = existing_nodes.get(conn.name)
            if node is not None:
                if node.parent is not parent:
                    try:
                        node.remove()
                    except Exception:
                        pass
                    node = None
                else:
                    label = (
                        host._format_connection_label(conn, "connected")
                        if is_connected
                        else host._format_connection_label(
                            conn,
                            "connecting" if is_connecting else "idle",
                            spinner=connecting_spinner if is_connecting else None,
                        )
                    )
                    node.set_label(label)
                    node.allow_expand = is_connected
                    node.data = ConnectionNode(config=conn)
                    existing_nodes[conn.name] = node

            if node is None:
                node = _add_connection_node(
                    host,
                    conn,
                    is_connected=is_connected,
                    is_connecting=is_connecting,
                    spinner=connecting_spinner if is_connecting else None,
                    skip_folder=skip_folder,
                )
                existing_nodes[conn.name] = node

        _cleanup_empty_folders(host)

        # Reorder nodes within each parent only when needed.
        for parent, desired_conns in desired_by_parent.items():
            desired_names = [conn.name for conn in desired_conns if conn is not None]
            existing_names: list[str] = []
            for child in parent.children:
                if host._get_node_kind(child) != "connection":
                    continue
                data = getattr(child, "data", None)
                config = getattr(data, "config", None)
                if config and config.name:
                    existing_names.append(config.name)
            if existing_names == desired_names:
                continue

            # Remove existing connection nodes under this parent.
            for child in list(parent.children):
                if host._get_node_kind(child) == "connection":
                    try:
                        child.remove()
                    except Exception:
                        pass

            # Re-add in desired order.
            for conn in desired_conns:
                if conn is None:
                    continue
                is_connected = host.current_config is not None and conn.name == host.current_config.name
                is_connecting = connecting_name == conn.name and not is_connected
                _add_connection_node(
                    host,
                    conn,
                    is_connected=is_connected,
                    is_connecting=is_connecting,
                    spinner=connecting_spinner if is_connecting else None,
                    skip_folder=exclusive_active,
                )

        if host.current_connection is not None and host.current_config is not None:
            populate_connected_tree(host)

        restore_subtree_expansion_with_paths(host, host.object_tree.root, expanded_snapshot)
        try:
            from . import loaders as tree_loaders
        except Exception:
            tree_loaders = None
        if tree_loaders is not None:
            tree_loaders.ensure_expanded_nodes_loaded(host, host.object_tree.root)

    if getattr(host, "_tree_refresh_token", None) is not token:
        return

    _restore_cursor(
        host,
        cursor_path=cursor_path,
        cursor_connection_name=cursor_connection_name,
    )

    if on_done:
        on_done()


def ensure_connecting_indicator(host: TreeMixinHost, config: Any) -> None:
    """Ensure a connecting node exists without rebuilding the tree."""
    spinner = host._connect_spinner_frame()
    label = host._format_connection_label(config, "connecting", spinner=spinner)
    node = _find_connection_node(host, config)
    if node is not None:
        node.set_label(label)
        node.allow_expand = False
        return
    node = _add_connection_node(
        host,
        config,
        is_connected=False,
        is_connecting=True,
        spinner=spinner,
    )
    node.allow_expand = False


def clear_connecting_indicator(host: TreeMixinHost, config: Any | None) -> None:
    """Clear connecting state without rebuilding the tree."""
    if config is None:
        return
    node = _find_connection_node(host, config)
    if node is None:
        return
    is_saved = any(c.name == config.name for c in host.connections)
    if host.current_config and host.current_config.name == config.name:
        label = host._format_connection_label(config, "connected")
        node.set_label(label)
        node.allow_expand = True
        return
    if is_saved:
        label = host._format_connection_label(config, "idle")
        node.set_label(label)
        node.allow_expand = False
        return
    try:
        node.remove()
    except Exception:
        pass


def schedule_populate_connected_tree(
    host: TreeMixinHost,
    *,
    on_done: Callable[[], None] | None = None,
) -> None:
    """Populate connected tree via idle scheduler with a timed fallback."""
    populate_token = object()
    setattr(host, "_populate_connected_token", populate_token)

    def populate_once() -> None:
        if getattr(host, "_populate_connected_token", None) is not populate_token:
            return
        setattr(host, "_populate_connected_token", None)
        populate_connected_tree(host)
        if on_done:
            on_done()

    try:
        from sqlit.domains.shell.app.idle_scheduler import Priority, get_idle_scheduler
    except Exception:
        scheduler = None
    else:
        scheduler = get_idle_scheduler()
    if scheduler:
        scheduler.cancel_all(name="populate-connected-tree")
        scheduler.request_idle_callback(
            populate_once,
            priority=Priority.HIGH,
            name="populate-connected-tree",
        )
    else:
        host.set_timer(MIN_TIMER_DELAY_S, populate_once)
    host.set_timer(POPULATE_CONNECTED_DEFER_S, populate_once)


def update_connecting_indicator(host: TreeMixinHost) -> None:
    connecting_config = getattr(host, "_connecting_config", None)
    if not connecting_config:
        return

    spinner = host._connect_spinner_frame()
    label = host._format_connection_label(connecting_config, "connecting", spinner=spinner)
    node = _find_connection_node(host, connecting_config)
    if node is not None:
        node.set_label(label)
        node.allow_expand = False


def refresh_tree(host: TreeMixinHost) -> None:
    """Refresh the explorer tree."""
    refresh_tree_incremental(host)


def refresh_tree_chunked(
    host: TreeMixinHost,
    *,
    batch_size: int = 10,
    on_done: Callable[[], None] | None = None,
) -> None:
    """Refresh the explorer tree in small batches to reduce UI stalls."""
    _ = batch_size
    refresh_tree_incremental(host, on_done=on_done)


def update_connection_state(
    host: TreeMixinHost,
    old_config: Any | None,
    new_config: Any | None,
) -> None:
    """Update tree to reflect connection state change without full rebuild.

    This is more efficient than refresh_tree when only the connection state changes.
    """
    # Update old connected node to idle state
    if old_config is not None:
        old_node = _find_connection_node(host, old_config)
        if old_node is not None:
            label = host._format_connection_label(old_config, "idle")
            old_node.set_label(label)
            old_node.allow_expand = False
            old_node.remove_children()

    # Update new connected node and populate it
    if new_config is not None and host.current_connection is not None:
        populate_connected_tree(host)


def remove_connection_nodes(host: TreeMixinHost, names: set[str]) -> None:
    """Remove connection nodes from the tree without full rebuild.

    Also cleans up any empty connection folders that result from the removal.
    """
    if not names:
        return

    # Find and remove the connection nodes
    nodes_to_remove: list[Any] = []
    stack = [host.object_tree.root]
    while stack:
        node = stack.pop()
        for child in node.children:
            if host._get_node_kind(child) == "connection":
                data = getattr(child, "data", None)
                node_config = getattr(data, "config", None)
                if node_config and node_config.name in names:
                    nodes_to_remove.append(child)
            stack.append(child)

    # Remove the nodes
    for node in nodes_to_remove:
        try:
            node.remove()
        except Exception:
            pass

    # Clean up empty connection folders
    _cleanup_empty_folders(host)


def _cleanup_empty_folders(host: TreeMixinHost) -> None:
    """Remove any empty connection folder nodes."""
    # Keep cleaning until no more empty folders found (handles nested folders)
    while True:
        empty_folders: list[Any] = []
        stack = [host.object_tree.root]
        while stack:
            node = stack.pop()
            for child in node.children:
                if host._get_node_kind(child) == "connection_folder":
                    if not child.children:
                        empty_folders.append(child)
                    else:
                        stack.append(child)
                else:
                    stack.append(child)

        if not empty_folders:
            break

        for folder in empty_folders:
            try:
                folder.remove()
            except Exception:
                pass


def populate_connected_tree(host: TreeMixinHost) -> None:
    """Populate tree with database objects when connected."""
    if (
        host.current_connection is None
        or host.current_config is None
        or host.current_provider is None
    ):
        return

    provider = host.current_provider
    def get_conn_label(config: Any, connected: bool = False) -> str:
        display_info = escape_markup(get_connection_display_info(config))
        db_type_label = host._db_type_badge(config.db_type)
        escaped_name = escape_markup(config.name)
        source_emoji = config.get_source_emoji() if hasattr(config, "get_source_emoji") else ""
        selected = getattr(host, "_selected_connection_names", set())
        selected_prefix = "[bright_cyan][x][/] " if config.name in selected else ""
        if connected:
            primary = getattr(getattr(host, "current_theme", None), "primary", "#7E9CD8")
            name = f"{selected_prefix}[{primary}]* {source_emoji}{escaped_name}[/]"
        else:
            name = f"{selected_prefix}{source_emoji}{escaped_name}"
        return f"{name} [{db_type_label}] ({display_info})"

    active_node = _find_connection_node(host, host.current_config)
    if active_node is not None:
        active_node.set_label(get_conn_label(host.current_config, connected=True))
    else:
        active_node = _add_connection_node(
            host,
            host.current_config,
            is_connected=True,
            is_connecting=False,
            spinner=None,
        )
        active_node.allow_expand = True

    active_node.remove_children()

    try:
        if provider.capabilities.supports_multiple_databases:
            endpoint = host.current_config.tcp_endpoint
            specific_db = endpoint.database if endpoint else ""
            show_single_db = specific_db and specific_db.lower() not in ("", "master")
            if show_single_db:
                add_database_object_nodes(host, active_node, specific_db)
                active_node.expand()
            else:
                dbs_node = active_node.add("Databases")
                dbs_node.data = FolderNode(folder_type="databases")
                dbs_node.allow_expand = True
                active_node.expand()
                # Trigger async load of databases so they're visible after refresh
                from . import loaders
                loaders.add_loading_placeholder(host, dbs_node)
                loaders.load_folder_async(host, dbs_node, dbs_node.data)
                dbs_node.expand()
        else:
            add_database_object_nodes(host, active_node, None)
            active_node.expand()

    except Exception as error:
        host.notify(f"Error loading objects: {error}", severity="error")


def add_database_object_nodes(host: TreeMixinHost, parent_node: Any, database: str | None) -> None:
    """Add Tables, Views, Indexes, Triggers, Sequences, and Stored Procedures nodes."""
    if not host.current_provider:
        return

    caps = host.current_provider.capabilities
    node_provider = host.current_provider.explorer_nodes

    for folder in node_provider.get_root_folders(caps):
        if folder.requires(caps):
            folder_node = parent_node.add(escape_markup(folder.label))
            folder_node.data = FolderNode(folder_type=folder.kind, database=database)
            folder_node.allow_expand = True
        else:
            parent_node.add_leaf(f"[dim]{folder.label} (Not available)[/]")
