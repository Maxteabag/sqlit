"""Tree construction helpers for explorer tree mixins."""

from __future__ import annotations

from typing import Any, Callable

from rich.markup import escape as escape_markup

from sqlit.domains.connections.providers.metadata import get_connection_display_info
from sqlit.domains.explorer.domain.tree_nodes import ConnectionFolderNode, ConnectionNode, FolderNode
from sqlit.domains.explorer.ui.tree.expansion_state import restore_subtree_expansion
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
    primary = getattr(getattr(host, "current_theme", None), "primary", "#7E9CD8")
    for part in folder_parts:
        node = _find_connection_folder_child(host, parent, part)
        if node is None:
            node = parent.add(f"[{primary}]📁 {part}[/]")
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
) -> Any:
    if is_connected:
        label = host._format_connection_label(config, "connected")
    elif is_connecting:
        label = host._format_connection_label(config, "connecting", spinner=spinner)
    else:
        label = host._format_connection_label(config, "idle")

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
    host.object_tree.clear()
    host.object_tree.root.expand()

    connecting_config = getattr(host, "_connecting_config", None)
    connecting_name = connecting_config.name if connecting_config else None
    connecting_spinner = host._connect_spinner_frame() if connecting_config else None

    # Check for active direct connection, exclusive connection, or pending startup connection
    direct_config = getattr(host, "_direct_connection_config", None)
    startup_config = getattr(host, "_startup_connect_config", None)
    exclusive_connection = getattr(host, "_exclusive_connection", False)
    direct_active = (
        direct_config is not None
        and host.current_config is not None
        and direct_config.name == host.current_config.name
    )
    # Hide saved connections when startup connection is pending (before it's connected)
    startup_pending = startup_config is not None and not any(
        c.name == startup_config.name for c in host.connections
    )
    # Exclusive mode: only show the specified connection (even if it's saved)
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
    _build_connection_folders(host, connections)

    for conn in connections:
        is_connected = host.current_config is not None and conn.name == host.current_config.name
        is_connecting = connecting_name == conn.name and not is_connected
        _add_connection_node(
            host,
            conn,
            is_connected=is_connected,
            is_connecting=is_connecting,
            spinner=connecting_spinner,
        )

    restore_subtree_expansion(host, host.object_tree.root)

    if host.current_connection is not None and host.current_config is not None:
        populate_connected_tree(host)


def refresh_tree_chunked(
    host: TreeMixinHost,
    *,
    batch_size: int = 10,
    on_done: Callable[[], None] | None = None,
) -> None:
    """Refresh the explorer tree in small batches to reduce UI stalls."""
    token = object()
    setattr(host, "_tree_refresh_token", token)

    host.object_tree.clear()
    host.object_tree.root.expand()

    connecting_config = getattr(host, "_connecting_config", None)
    connecting_name = connecting_config.name if connecting_config else None
    connecting_spinner = host._connect_spinner_frame() if connecting_config else None

    # Check for active direct connection, exclusive connection, or pending startup connection
    direct_config = getattr(host, "_direct_connection_config", None)
    startup_config = getattr(host, "_startup_connect_config", None)
    exclusive_connection = getattr(host, "_exclusive_connection", False)
    direct_active = (
        direct_config is not None
        and host.current_config is not None
        and direct_config.name == host.current_config.name
    )
    # Hide saved connections when startup connection is pending (before it's connected)
    startup_pending = startup_config is not None and not any(
        c.name == startup_config.name for c in host.connections
    )
    # Exclusive mode: only show the specified connection (even if it's saved)
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
    _build_connection_folders(host, connections)

    def schedule_populate() -> None:
        if getattr(host, "_tree_refresh_token", None) is not token:
            return

        def populate_and_done() -> None:
            if getattr(host, "_tree_refresh_token", None) is not token:
                return
            if host.current_connection is not None and host.current_config is not None:
                populate_connected_tree(host)
            if on_done:
                on_done()

        if host.current_connection is not None and host.current_config is not None:
            populate_token = object()
            setattr(host, "_populate_connected_token", populate_token)

            def populate_once() -> None:
                if getattr(host, "_tree_refresh_token", None) is not token:
                    return
                if getattr(host, "_populate_connected_token", None) is not populate_token:
                    return
                setattr(host, "_populate_connected_token", None)
                populate_and_done()

            try:
                from sqlit.domains.shell.app.idle_scheduler import (
                    Priority,
                    get_idle_scheduler,
                )
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
        else:
            if on_done:
                on_done()

    if len(connections) <= MAX_SYNC_CONNECTIONS:
        for conn in connections:
            is_connected = host.current_config is not None and conn.name == host.current_config.name
            is_connecting = connecting_name == conn.name and not is_connected
            _add_connection_node(
                host,
                conn,
                is_connected=is_connected,
                is_connecting=is_connecting,
                spinner=connecting_spinner,
            )

        def finish_sync() -> None:
            restore_subtree_expansion(host, host.object_tree.root)
            schedule_populate()

        host.set_timer(MIN_TIMER_DELAY_S, finish_sync)
        return

    batch_size = max(1, int(batch_size))
    idx = 0

    def add_batch() -> None:
        nonlocal idx
        if getattr(host, "_tree_refresh_token", None) is not token:
            return
        end = min(idx + batch_size, len(connections))
        for conn in connections[idx:end]:
            is_connected = host.current_config is not None and conn.name == host.current_config.name
            is_connecting = connecting_name == conn.name and not is_connected
            _add_connection_node(
                host,
                conn,
                is_connected=is_connected,
                is_connecting=is_connecting,
                spinner=connecting_spinner,
            )
        idx = end
        if idx < len(connections):
            host.set_timer(MIN_TIMER_DELAY_S, add_batch)
            return

        def finish() -> None:
            restore_subtree_expansion(host, host.object_tree.root)
            schedule_populate()

        host.set_timer(MIN_TIMER_DELAY_S, finish)

    add_batch()


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

    primary = getattr(getattr(host, "current_theme", None), "primary", "#7E9CD8")
    for folder in node_provider.get_root_folders(caps):
        if folder.requires(caps):
            folder_node = parent_node.add(f"[{primary}]{folder.label}[/]")
            folder_node.data = FolderNode(folder_type=folder.kind, database=database)
            folder_node.allow_expand = True
        else:
            parent_node.add_leaf(f"[dim]{folder.label} (Not available)[/]")
