"""Database switching helpers for explorer tree mixins."""

from __future__ import annotations

from rich.markup import escape as escape_markup

from sqlit.shared.ui.protocols import TreeMixinHost


def ensure_database_connection(host: TreeMixinHost, target_db: str) -> bool:
    """Ensure we're connected to the target database, switching if needed."""
    if not host.current_provider or not host.current_config:
        return False

    if host.current_provider.capabilities.supports_cross_database_queries:
        current_active = getattr(host, "_active_database", None)
        if not current_active or current_active.lower() != target_db.lower():
            try:
                set_default_database(host, target_db)
            except Exception:
                reconnect_to_database(host, target_db)
        return True

    endpoint = host.current_config.tcp_endpoint
    current_db = endpoint.database if endpoint else ""
    if current_db and current_db.lower() == target_db.lower():
        return True

    set_default_database(host, target_db)

    endpoint = host.current_config.tcp_endpoint
    return bool(endpoint and endpoint.database and endpoint.database.lower() == target_db.lower())


def reconnect_to_database(host: TreeMixinHost, db_name: str) -> None:
    """Reconnect to a different database without re-rendering the tree."""
    if not host._session:
        return

    if hasattr(host, "_clear_query_target_database"):
        host._clear_query_target_database()

    try:
        host._session.switch_database(db_name)

        host.current_config = host._session.config
        host.current_connection = host._session.connection

        host.notify(f"Switched to database: {db_name}")
        host._update_status_bar()
        update_database_labels(host)

        host._get_object_cache().clear()
        host._load_schema_cache()

    except Exception as error:
        host.notify(f"Failed to connect to {db_name}: {error}", severity="error")


def set_default_database(host: TreeMixinHost, db_name: str | None) -> None:
    """Set or clear the active database for the current connection."""
    if not host.current_config or not host.current_provider:
        host.notify("Not connected", severity="error")
        return

    if hasattr(host, "_clear_query_target_database"):
        host._clear_query_target_database()

    if not host.current_provider.capabilities.supports_cross_database_queries and db_name:
        endpoint = host.current_config.tcp_endpoint
        current_db = endpoint.database if endpoint else ""
        if current_db and current_db.lower() == db_name.lower():
            host._active_database = db_name
            host._update_status_bar()
            update_database_labels(host)
            return

        reconnect_to_database(host, db_name)
        return

    host._active_database = db_name
    if db_name:
        host.notify(f"Switched to database: {db_name}")
    else:
        host.notify("Cleared default database")
    host._update_status_bar()
    update_database_labels(host)
    host._load_schema_cache()


def update_database_labels(host: TreeMixinHost) -> None:
    """Update database node labels to show the active database with a star."""
    if not host.current_config or not host.current_provider:
        return

    active_db = None
    if hasattr(host, "_get_effective_database"):
        active_db = host._get_effective_database()

    target_node = None
    stack = [host.object_tree.root]
    while stack:
        node = stack.pop()
        for child in node.children:
            if host._get_node_kind(child) == "connection":
                conn_data = getattr(child, "data", None)
                conn_config = getattr(conn_data, "config", None)
                if conn_config and conn_config.name == host.current_config.name:
                    target_node = child
                    break
            stack.append(child)
        if target_node is not None:
            break

    if target_node is None:
        return

    for child in target_node.children:
        child_data = getattr(child, "data", None)
        folder_type = getattr(child_data, "folder_type", None)
        if host._get_node_kind(child) == "folder" and folder_type == "databases":
            for db_node in child.children:
                if host._get_node_kind(db_node) == "database":
                    db_data = getattr(db_node, "data", None)
                    db_name = getattr(db_data, "name", None)
                    if not db_name:
                        continue
                    is_active = active_db and db_name.lower() == active_db.lower()
                    if is_active:
                        db_node.set_label(f"[#4ADE80]* {escape_markup(db_name)}[/]")
                    else:
                        db_node.set_label(escape_markup(db_name))
            break
