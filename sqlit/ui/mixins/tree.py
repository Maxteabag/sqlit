"""Tree/Explorer mixin for SSMSTUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.markup import escape as escape_markup
from textual.widgets import Tree

from ..protocols import AppProtocol
from .query import SPINNER_FRAMES
from ...db.providers import get_badge_label, get_connection_display_info
from ..tree_nodes import (
    ColumnNode,
    ConnectionNode,
    DatabaseNode,
    FolderNode,
    IndexNode,
    LoadingNode,
    ProcedureNode,
    SchemaNode,
    SequenceNode,
    TableNode,
    TriggerNode,
    ViewNode,
)

if TYPE_CHECKING:
    pass


class TreeMixin:
    """Mixin providing tree/explorer functionality."""

    def _run_db_call(self: AppProtocol, fn: Any, *args: Any, **kwargs: Any) -> Any:
        session = getattr(self, "_session", None)
        if session is not None:
            return session.executor.submit(fn, *args, **kwargs).result()
        return fn(*args, **kwargs)

    def _db_type_badge(self, db_type: str) -> str:
        """Get short badge for database type."""
        return get_badge_label(db_type)

    def _format_connection_label(self, conn: Any, status: str, spinner: str | None = None) -> str:
        display_info = escape_markup(get_connection_display_info(conn))
        db_type_label = self._db_type_badge(conn.db_type)
        escaped_name = escape_markup(conn.name)
        source_emoji = conn.get_source_emoji()

        if status == "connected":
            return f"[#4ADE80]* {source_emoji}{escaped_name}[/] [{db_type_label}] ({display_info})"
        if status == "connecting":
            frame = spinner or SPINNER_FRAMES[0]
            return (
                f"[#FBBF24]{frame}[/] {source_emoji}{escaped_name} [dim italic]Connecting...[/]"
            )
        return f"{source_emoji}[dim]{escaped_name}[/dim] [{db_type_label}] ({display_info})"

    def _connect_spinner_frame(self) -> str:
        idx = getattr(self, "_connect_spinner_index", 0)
        return SPINNER_FRAMES[idx % len(SPINNER_FRAMES)]

    def _get_node_kind(self, node: Any) -> str:
        data = getattr(node, "data", None)
        if data is None:
            return ""
        getter = getattr(data, "get_node_kind", None)
        if callable(getter):
            return str(getter())
        return ""

    def _get_node_path_part(self, data: Any) -> str:
        getter = getattr(data, "get_node_path_part", None)
        if callable(getter):
            return str(getter())
        return ""

    def _update_connecting_indicator(self: AppProtocol) -> None:
        connecting_config = getattr(self, "_connecting_config", None)
        if not connecting_config:
            return

        spinner = self._connect_spinner_frame()
        label = self._format_connection_label(connecting_config, "connecting", spinner=spinner)

        for node in self.object_tree.root.children:
            if self._get_node_kind(node) == "connection" and node.data.config.name == connecting_config.name:
                node.set_label(label)
                node.allow_expand = False
                break

    def refresh_tree(self: AppProtocol) -> None:
        """Refresh the explorer tree."""
        self.object_tree.clear()
        self.object_tree.root.expand()

        connecting_config = getattr(self, "_connecting_config", None)
        connecting_name = connecting_config.name if connecting_config else None
        connecting_spinner = self._connect_spinner_frame() if connecting_config else None

        direct_config = getattr(self, "_direct_connection_config", None)
        direct_active = (
            direct_config is not None
            and self.current_config is not None
            and direct_config.name == self.current_config.name
        )
        connections = [self.current_config] if direct_active else self.connections
        if connecting_config and not any(c.name == connecting_config.name for c in connections):
            connections = connections + [connecting_config]

        for conn in connections:
            # Check if this is the connected server
            is_connected = (
                self.current_config is not None
                and conn.name == self.current_config.name
            )
            is_connecting = connecting_name == conn.name and not is_connected
            if is_connected:
                label = self._format_connection_label(conn, "connected")
            elif is_connecting:
                label = self._format_connection_label(conn, "connecting", spinner=connecting_spinner)
            else:
                label = self._format_connection_label(conn, "idle")
            node = self.object_tree.root.add(label)
            node.data = ConnectionNode(config=conn)
            node.allow_expand = is_connected

        if self.current_connection and self.current_config:
            self.populate_connected_tree()

    def populate_connected_tree(self: AppProtocol) -> None:
        """Populate tree with database objects when connected."""
        if not self.current_connection or not self.current_config or not self.current_adapter:
            return

        adapter = self.current_adapter

        def get_conn_label(config: Any, connected: Any = False) -> str:
            display_info = escape_markup(get_connection_display_info(config))
            db_type_label = self._db_type_badge(config.db_type)
            escaped_name = escape_markup(config.name)
            source_emoji = config.get_source_emoji() if hasattr(config, "get_source_emoji") else ""
            if connected:
                name = f"[#4ADE80]* {source_emoji}{escaped_name}[/]"
            else:
                name = f"{source_emoji}{escaped_name}"
            return f"{name} [{db_type_label}] ({display_info})"

        active_node = None
        for child in self.object_tree.root.children:
            if self._get_node_kind(child) == "connection":
                if child.data.config.name == self.current_config.name:
                    child.set_label(get_conn_label(self.current_config, connected=True))
                    active_node = child
                    break

        if not active_node:
            active_node = self.object_tree.root.add(get_conn_label(self.current_config, connected=True))
            active_node.data = ConnectionNode(config=self.current_config)
            active_node.allow_expand = True

        active_node.remove_children()

        try:
            if adapter.supports_multiple_databases:
                specific_db = self.current_config.database
                # For adapters that don't support cross-database queries (PostgreSQL, etc.),
                # always show the Databases folder so users can switch between databases.
                # For adapters that do support cross-database queries (SQL Server, MySQL),
                # show single database view only if a specific database was configured.
                show_single_db = (
                    specific_db
                    and specific_db.lower() not in ("", "master")
                    and adapter.supports_cross_database_queries
                )
                if show_single_db:
                    self._add_database_object_nodes(active_node, specific_db)
                    active_node.expand()
                else:
                    dbs_node = active_node.add("Databases")
                    dbs_node.data = FolderNode(folder_type="databases")

                    databases = self._run_db_call(adapter.get_databases, self.current_connection)
                    active_db = None
                    if hasattr(self, "_get_effective_database"):
                        active_db = self._get_effective_database()
                    for db_name in databases:
                        # Show active database with star and green text
                        if active_db and db_name.lower() == active_db.lower():
                            db_label = f"[#4ADE80]* {escape_markup(db_name)}[/]"
                        else:
                            db_label = escape_markup(db_name)
                        db_node = dbs_node.add(db_label)
                        db_node.data = DatabaseNode(name=db_name)
                        db_node.allow_expand = True
                        self._add_database_object_nodes(db_node, db_name)

                    active_node.expand()
                    dbs_node.expand()
            else:
                self._add_database_object_nodes(active_node, None)
                active_node.expand()

            self.call_later(lambda: self._restore_subtree_expansion(active_node))

        except Exception as e:
            self.notify(f"Error loading objects: {e}", severity="error")

    def _add_database_object_nodes(self: AppProtocol, parent_node: Any, database: str | None) -> None:
        """Add Tables, Views, Indexes, Triggers, Sequences, and Stored Procedures nodes."""
        tables_node = parent_node.add("Tables")
        tables_node.data = FolderNode(folder_type="tables", database=database)
        tables_node.allow_expand = True

        views_node = parent_node.add("Views")
        views_node.data = FolderNode(folder_type="views", database=database)
        views_node.allow_expand = True

        def add_optional_folder(
            label: str, folder_type: str, supported: bool | None
        ) -> None:
            if supported:
                folder_node = parent_node.add(label)
                folder_node.data = FolderNode(folder_type=folder_type, database=database)
                folder_node.allow_expand = True
            else:
                parent_node.add_leaf(f"[dim]{label} (Not available)[/]")

        add_optional_folder(
            "Indexes",
            "indexes",
            self.current_adapter.supports_indexes if self.current_adapter else None,
        )
        add_optional_folder(
            "Triggers",
            "triggers",
            self.current_adapter.supports_triggers if self.current_adapter else None,
        )
        add_optional_folder(
            "Sequences",
            "sequences",
            self.current_adapter.supports_sequences if self.current_adapter else None,
        )
        add_optional_folder(
            "Stored Procedures",
            "procedures",
            self.current_adapter.supports_stored_procedures if self.current_adapter else None,
        )

    def _get_node_path(self, node: Any) -> str:
        """Get a unique path string for a tree node."""
        parts = []
        current = node
        while current and current.parent:
            data = current.data
            if data:
                path_part = self._get_node_path_part(data)
                if path_part:
                    parts.append(path_part)
            current = current.parent
        return "/".join(reversed(parts))

    def _restore_subtree_expansion(self: AppProtocol, node: Any) -> None:
        """Recursively expand nodes that should be expanded."""
        for child in node.children:
            if child.data:
                path = self._get_node_path(child)
                if path in self._expanded_paths:
                    child.expand()
            self._restore_subtree_expansion(child)

    def _save_expanded_state(self: AppProtocol) -> None:
        """Save which nodes are expanded."""
        from ...config import load_settings, save_settings

        expanded = []

        def collect_expanded(node: Any) -> None:
            if node.is_expanded and node.data:
                path = self._get_node_path(node)
                if path:
                    expanded.append(path)
            for child in node.children:
                collect_expanded(child)

        collect_expanded(self.object_tree.root)

        self._expanded_paths = set(expanded)
        settings = load_settings()
        settings["expanded_nodes"] = expanded
        save_settings(settings)

    def on_tree_node_collapsed(self: AppProtocol, event: Tree.NodeCollapsed) -> None:
        """Save state when a node is collapsed."""
        self.call_later(self._save_expanded_state)

    def on_tree_node_expanded(self: AppProtocol, event: Tree.NodeExpanded) -> None:
        """Load child objects when a node is expanded."""
        node = event.node

        self.call_later(self._save_expanded_state)

        if not node.data or not self.current_connection or not self.current_adapter:
            return

        data = node.data

        # When a database node is expanded, ensure we're connected to it
        if self._get_node_kind(node) == "database":
            self._ensure_database_connection(data.name)

        # Skip if already has children (not just loading placeholder)
        children = list(node.children)
        if children:
            # Check if it's just a loading placeholder
            if len(children) == 1 and self._get_node_kind(children[0]) == "loading":
                return  # Already loading
            if self._get_node_kind(children[0]) != "loading":
                return  # Already loaded

        # Initialize _loading_nodes if not present
        if not hasattr(self, "_loading_nodes") or self._loading_nodes is None:
            self._loading_nodes = set()

        # Get node path to track loading state
        node_path = self._get_node_path(node)
        if node_path in self._loading_nodes:
            return  # Already loading this node

        # Handle table/view column expansion
        if self._get_node_kind(node) in ("table", "view"):
            # Ensure we're connected to the right database before loading
            target_db = data.database
            if target_db and not self._ensure_database_connection(target_db):
                return  # Switch failed
            self._loading_nodes.add(node_path)
            loading_node = node.add_leaf("[dim italic]Loading...[/]")
            loading_node.data = LoadingNode()
            self._load_columns_async(node, data)
            return

        # Handle folder expansion (database can be None for single-db adapters)
        if self._get_node_kind(node) == "folder":
            # Ensure we're connected to the right database before loading
            target_db = data.database
            if target_db and not self._ensure_database_connection(target_db):
                return  # Switch failed
            self._loading_nodes.add(node_path)
            loading_node = node.add_leaf("[dim italic]Loading...[/]")
            loading_node.data = LoadingNode()
            self._load_folder_async(node, data)
            return

    def _load_columns_async(self: AppProtocol, node: Any, data: TableNode | ViewNode) -> None:
        """Spawn worker to load columns for a table/view."""
        db_name = data.database
        schema_name = data.schema
        obj_name = data.name

        def work() -> None:
            """Run in worker thread."""
            try:
                if not self._session:
                    columns = []
                else:
                    adapter = self._session.adapter
                    conn = self._session.connection
                    db_arg = db_name
                    if hasattr(self, "_get_metadata_db_arg"):
                        db_arg = self._get_metadata_db_arg(db_name)
                    columns = self._run_db_call(adapter.get_columns, conn, obj_name, db_arg, schema_name)

                # Update UI from worker thread
                self.call_from_thread(self._on_columns_loaded, node, db_name, schema_name, obj_name, columns)
            except Exception as e:
                self.call_from_thread(self._on_tree_load_error, node, f"Error loading columns: {e}")

        self.run_worker(work, name=f"load-columns-{obj_name}", thread=True, exclusive=False)

    def _on_columns_loaded(
        self: AppProtocol, node: Any, db_name: str | None, schema_name: str, obj_name: str, columns: list
    ) -> None:
        """Handle column load completion on main thread."""
        node_path = self._get_node_path(node)
        self._loading_nodes.discard(node_path)

        for child in list(node.children):
            if self._get_node_kind(child) == "loading":
                child.remove()

        if not columns:
            empty_child = node.add_leaf("[dim](Empty)[/]")
            empty_child.data = LoadingNode()
            return

        for col in columns:
            col_name = escape_markup(col.name)
            col_type = escape_markup(col.data_type)
            child = node.add_leaf(f"[dim]{col_name}[/] [italic dim]{col_type}[/]")
            child.data = ColumnNode(database=db_name, schema=schema_name, table=obj_name, name=col.name)

    def _load_folder_async(self: AppProtocol, node: Any, data: FolderNode) -> None:
        """Spawn worker to load folder contents (tables/views/indexes/triggers/sequences/procedures)."""
        folder_type = data.folder_type
        db_name = data.database
        cache_key = db_name or "__default__"

        def work() -> None:
            """Run in worker thread."""
            try:
                if not self._session:
                    items = []
                else:
                    adapter = self._session.adapter
                    conn = self._session.connection
                    db_arg = db_name
                    if hasattr(self, "_get_metadata_db_arg"):
                        db_arg = self._get_metadata_db_arg(db_name)

                    # Check shared cache first for tables/views/procedures
                    obj_cache = getattr(self, "_db_object_cache", {})

                    if folder_type == "tables":
                        if cache_key in obj_cache and "tables" in obj_cache[cache_key]:
                            raw_data = obj_cache[cache_key]["tables"]
                        else:
                            raw_data = self._run_db_call(adapter.get_tables, conn, db_arg)
                            # Store in shared cache
                            if cache_key not in obj_cache:
                                obj_cache[cache_key] = {}
                            obj_cache[cache_key]["tables"] = raw_data
                            self._db_object_cache = obj_cache
                        items = [("table", s, t) for s, t in raw_data]
                    elif folder_type == "views":
                        if cache_key in obj_cache and "views" in obj_cache[cache_key]:
                            raw_data = obj_cache[cache_key]["views"]
                        else:
                            raw_data = self._run_db_call(adapter.get_views, conn, db_arg)
                            # Store in shared cache
                            if cache_key not in obj_cache:
                                obj_cache[cache_key] = {}
                            obj_cache[cache_key]["views"] = raw_data
                            self._db_object_cache = obj_cache
                        items = [("view", s, v) for s, v in raw_data]
                    elif folder_type == "indexes":
                        if adapter.supports_indexes:
                            items = [
                                ("index", i.name, i.table_name)
                                for i in self._run_db_call(adapter.get_indexes, conn, db_arg)
                            ]
                        else:
                            items = []
                    elif folder_type == "triggers":
                        if adapter.supports_triggers:
                            items = [
                                ("trigger", t.name, t.table_name)
                                for t in self._run_db_call(adapter.get_triggers, conn, db_arg)
                            ]
                        else:
                            items = []
                    elif folder_type == "sequences":
                        if adapter.supports_sequences:
                            items = [
                                ("sequence", s.name, "")
                                for s in self._run_db_call(adapter.get_sequences, conn, db_arg)
                            ]
                        else:
                            items = []
                    elif folder_type == "procedures":
                        if adapter.supports_stored_procedures:
                            if cache_key in obj_cache and "procedures" in obj_cache[cache_key]:
                                raw_data = obj_cache[cache_key]["procedures"]
                            else:
                                raw_data = self._run_db_call(adapter.get_procedures, conn, db_arg)
                                # Store in shared cache
                                if cache_key not in obj_cache:
                                    obj_cache[cache_key] = {}
                                obj_cache[cache_key]["procedures"] = raw_data
                                self._db_object_cache = obj_cache
                            items = [("procedure", "", p) for p in raw_data]
                        else:
                            items = []
                    else:
                        items = []

                # Update UI from worker thread
                self.call_from_thread(self._on_folder_loaded, node, db_name, folder_type, items)
            except Exception as e:
                # If we have a target database, try reconnecting as fallback (handles Azure SQL etc.)
                if db_name:
                    self.call_from_thread(self._fallback_reconnect_and_retry, node, data, db_name, e)
                else:
                    self.call_from_thread(self._on_tree_load_error, node, f"Error loading: {e}")

        self.run_worker(work, name=f"load-folder-{folder_type}", thread=True, exclusive=False)

    def _on_folder_loaded(self: AppProtocol, node: Any, db_name: str | None, folder_type: str, items: list) -> None:
        """Handle folder load completion on main thread."""
        node_path = self._get_node_path(node)
        self._loading_nodes.discard(node_path)

        for child in list(node.children):
            if self._get_node_kind(child) == "loading":
                child.remove()

        if not self._session:
            return

        adapter = self._session.adapter
        if not items:
            empty_child = node.add_leaf("[dim](Empty)[/]")
            empty_child.data = LoadingNode()
            return

        if folder_type in ("tables", "views"):
            self._add_schema_grouped_items(node, db_name, folder_type, items, adapter.default_schema)
        else:
            for item in items:
                if item[0] == "procedure":
                    child = node.add_leaf(escape_markup(item[2]))
                    child.data = ProcedureNode(database=db_name, name=item[2])
                elif item[0] == "index":
                    # Display as "index_name (table_name)" - leaf node, no children
                    display = f"{escape_markup(item[1])} [dim]({escape_markup(item[2])})[/]"
                    child = node.add_leaf(display)
                    child.data = IndexNode(database=db_name, name=item[1], table_name=item[2])
                elif item[0] == "trigger":
                    # Display as "trigger_name (table_name)" - leaf node, no children
                    display = f"{escape_markup(item[1])} [dim]({escape_markup(item[2])})[/]"
                    child = node.add_leaf(display)
                    child.data = TriggerNode(database=db_name, name=item[1], table_name=item[2])
                elif item[0] == "sequence":
                    # Leaf node, no children
                    child = node.add_leaf(escape_markup(item[1]))
                    child.data = SequenceNode(database=db_name, name=item[1])

    def _add_schema_grouped_items(
        self,
        node: Any,
        db_name: str | None,
        folder_type: str,
        items: list[Any],
        default_schema: str,
    ) -> None:
        """Add tables/views grouped by schema."""
        from collections import defaultdict

        by_schema: dict[str, list] = defaultdict(list)
        for item in items:
            by_schema[item[1]].append(item)

        def schema_sort_key(schema: str) -> tuple[int, str]:
            if not schema or schema == default_schema:
                return (0, schema)
            return (1, schema.lower())

        sorted_schemas = sorted(by_schema.keys(), key=schema_sort_key)
        has_multiple_schemas = len(sorted_schemas) > 1
        schema_nodes: dict[str, Any] = {}

        for schema in sorted_schemas:
            schema_items = by_schema[schema]
            is_default = not schema or schema == default_schema

            if is_default and not has_multiple_schemas:
                parent = node
            else:
                if schema not in schema_nodes:
                    display_name = schema if schema else default_schema
                    escaped_name = escape_markup(display_name)
                    schema_node = node.add(f"[dim]\\[{escaped_name}][/]")
                    schema_node.data = SchemaNode(
                        database=db_name, schema=schema or default_schema, folder_type=folder_type
                    )
                    schema_node.allow_expand = True
                    schema_nodes[schema] = schema_node
                parent = schema_nodes[schema]

            for item in schema_items:
                item_type, schema_name, obj_name = item[0], item[1], item[2]
                child = parent.add(escape_markup(obj_name))
                if item_type == "table":
                    child.data = TableNode(database=db_name, schema=schema_name, name=obj_name)
                else:
                    child.data = ViewNode(database=db_name, schema=schema_name, name=obj_name)
                child.allow_expand = True

    def _on_tree_load_error(self: AppProtocol, node: Any, error_message: str) -> None:
        """Handle tree load error on main thread."""
        node_path = self._get_node_path(node)
        self._loading_nodes.discard(node_path)

        for child in list(node.children):
            if self._get_node_kind(child) == "loading":
                child.remove()

        self.notify(escape_markup(error_message), severity="error")

    def _fallback_reconnect_and_retry(
        self: AppProtocol, node: Any, data: FolderNode, db_name: str, original_error: Exception
    ) -> None:
        """Try reconnecting to database and retry loading. Show original error if this also fails."""
        node_path = self._get_node_path(node)
        self._loading_nodes.discard(node_path)

        # Remove loading placeholder
        for child in list(node.children):
            if self._get_node_kind(child) == "loading":
                child.remove()

        # Try to reconnect
        try:
            self._reconnect_to_database(db_name)
        except Exception:
            # Reconnect failed - show original error
            self.notify(escape_markup(f"Error loading: {original_error}"), severity="error")
            return

        # Reconnect succeeded - retry loading
        self._loading_nodes.add(node_path)
        loading_node = node.add_leaf("[dim italic]Loading...[/]")
        loading_node.data = LoadingNode()
        self._load_folder_async(node, data)

    def on_tree_node_selected(self: AppProtocol, event: Tree.NodeSelected) -> None:
        """Handle tree node selection (double-click/enter)."""
        # Ignore selection events when tree filter is active - the filter captures
        # printable characters, but Textual's Tree type-ahead may fire NodeSelected
        # before on_key can stop the event
        if getattr(self, "_tree_filter_visible", False):
            return

        node = event.node
        if not node.data:
            return

        data = node.data

        if self._get_node_kind(node) == "connection":
            config = data.config
            if self.current_config and self.current_config.name == config.name:
                return
            # _disconnect_silent handles refresh_tree internally
            self.connect_to_server(config)

    def on_tree_node_highlighted(self: AppProtocol, event: Tree.NodeHighlighted) -> None:
        """Update footer when tree selection changes."""
        self._update_footer_bindings()

    def action_refresh_tree(self: AppProtocol) -> None:
        """Refresh the explorer."""
        # Clear shared object cache so fresh data is fetched
        self._db_object_cache = {}
        # Clear column cache too so columns are re-fetched
        if hasattr(self, "_schema_cache") and "columns" in self._schema_cache:
            self._schema_cache["columns"] = {}
        self.refresh_tree()
        self.notify("Refreshed")

    def action_collapse_tree(self: AppProtocol) -> None:
        """Collapse all nodes in the explorer."""

        def collapse_all(node: Any) -> None:
            for child in node.children:
                collapse_all(child)
                child.collapse()

        collapse_all(self.object_tree.root)
        self._expanded_paths.clear()
        self._save_expanded_state()

    def action_tree_cursor_down(self: AppProtocol) -> None:
        """Move tree cursor down (vim j)."""
        if self.object_tree.has_focus:
            self.object_tree.action_cursor_down()

    def action_tree_cursor_up(self: AppProtocol) -> None:
        """Move tree cursor up (vim k)."""
        if self.object_tree.has_focus:
            self.object_tree.action_cursor_up()

    def action_select_table(self: AppProtocol) -> None:
        """Generate and execute SELECT query for selected table/view, or show info for indexes/triggers/sequences."""
        if not self.current_adapter or not self._session:
            return

        node = self.object_tree.cursor_node

        if not node or not node.data:
            return

        data = node.data

        # Handle table/view - execute SELECT query
        if self._get_node_kind(node) in ("table", "view"):
            # Store table info for edit_cell action
            try:
                db_arg = data.database
                if hasattr(self, "_get_metadata_db_arg"):
                    db_arg = self._get_metadata_db_arg(data.database)
                columns = self._session.adapter.get_columns(
                    self._session.connection, data.name, db_arg, data.schema
                )
                self._last_query_table = {
                    "database": data.database,
                    "schema": data.schema,
                    "name": data.name,
                    "columns": columns,
                }
            except Exception:
                self._last_query_table = None

            self.query_input.text = self.current_adapter.build_select_query(data.name, 100, data.database, data.schema)
            # Set target database for query execution (needed for Azure SQL)
            self._query_target_database = data.database
            self.action_execute_query()
            return

        # Handle index - show index definition
        if self._get_node_kind(node) == "index":
            self._show_index_info(data)
            return

        # Handle trigger - show trigger definition
        if self._get_node_kind(node) == "trigger":
            self._show_trigger_info(data)
            return

        # Handle sequence - show sequence info
        if self._get_node_kind(node) == "sequence":
            self._show_sequence_info(data)
            return

    def _show_index_info(self: AppProtocol, data: IndexNode) -> None:
        """Show index definition in the results panel."""
        if not self._session:
            return

        try:
            db_arg = data.database
            if hasattr(self, "_get_metadata_db_arg"):
                db_arg = self._get_metadata_db_arg(data.database)
            info = self._session.adapter.get_index_definition(
                self._session.connection, data.name, data.table_name, db_arg
            )
            self._display_object_info("Index", info)
        except Exception as e:
            self.notify(f"Error getting index info: {e}", severity="error")

    def _show_trigger_info(self: AppProtocol, data: TriggerNode) -> None:
        """Show trigger definition in the results panel."""
        if not self._session:
            return

        try:
            db_arg = data.database
            if hasattr(self, "_get_metadata_db_arg"):
                db_arg = self._get_metadata_db_arg(data.database)
            info = self._session.adapter.get_trigger_definition(
                self._session.connection, data.name, data.table_name, db_arg
            )
            self._display_object_info("Trigger", info)
        except Exception as e:
            self.notify(f"Error getting trigger info: {e}", severity="error")

    def _show_sequence_info(self: AppProtocol, data: SequenceNode) -> None:
        """Show sequence information in the results panel."""
        if not self._session:
            return

        try:
            db_arg = data.database
            if hasattr(self, "_get_metadata_db_arg"):
                db_arg = self._get_metadata_db_arg(data.database)
            info = self._session.adapter.get_sequence_definition(
                self._session.connection, data.name, db_arg
            )
            self._display_object_info("Sequence", info)
        except Exception as e:
            self.notify(f"Error getting sequence info: {e}", severity="error")

    def _display_object_info(self: AppProtocol, object_type: str, info: dict) -> None:
        """Display object info in the results table as a Property/Value view."""
        # Build rows for display
        rows: list[tuple[str, str]] = []
        for key, value in info.items():
            if value is not None:
                # Format the key nicely
                display_key = key.replace("_", " ").title()
                # Handle lists (like columns)
                if isinstance(value, list):
                    display_value = ", ".join(str(v) for v in value) if value else "(none)"
                # Handle booleans
                elif isinstance(value, bool):
                    display_value = "Yes" if value else "No"
                else:
                    display_value = str(value)
                rows.append((display_key, display_value))

        # Update the results table using the helper method
        self._replace_results_table(["Property", "Value"], rows)  # type: ignore[attr-defined]

        # Store for copy/export functionality
        self._last_result_columns = ["Property", "Value"]
        self._last_result_rows = rows
        self._last_result_row_count = len(rows)

        self.notify(f"{object_type}: {info.get('name', 'Unknown')}")

        # Also show the definition in the query input if available
        definition = info.get("definition")
        if definition:
            self.query_input.text = f"/*\n{definition}\n*/"

    def _ensure_database_connection(self: AppProtocol, target_db: str) -> bool:
        """Ensure we're connected to the target database, switching if needed.

        For adapters that don't support cross-database queries (PostgreSQL, etc.),
        this will switch the connection if we're not already connected to the
        target database.

        Args:
            target_db: The database name we need to be connected to.

        Returns:
            True if we're connected to the target database (or adapter supports
            cross-db queries), False if switch failed.
        """
        if not self.current_adapter or not self.current_config:
            return False

        # For cross-db adapters, try USE approach first (no reconnection needed).
        # Note: While MSSQL generally supports cross-database queries, some variants
        # like Azure SQL have restrictions. If USE fails, we fall back to reconnection.
        if self.current_adapter.supports_cross_database_queries:
            current_active = getattr(self, "_active_database", None)
            if not current_active or current_active.lower() != target_db.lower():
                try:
                    self.set_default_database(target_db)
                except Exception:
                    # USE approach failed - fall back to reconnection
                    self._reconnect_to_database(target_db)
            return True

        # For non-cross-db adapters, check if already connected to target database
        current_db = self.current_config.database
        if current_db and current_db.lower() == target_db.lower():
            return True

        # Need to reconnect - set_default_database handles this
        self.set_default_database(target_db)

        # Verify switch succeeded
        return (
            self.current_config.database is not None
            and self.current_config.database.lower() == target_db.lower()
        )

    def _reconnect_to_database(self: AppProtocol, db_name: str) -> None:
        """Reconnect to a different database without re-rendering the tree.

        Used for PostgreSQL and other databases that don't support cross-database
        queries. Creates a new connection to the specified database while keeping
        the tree structure intact.
        """
        from ...config import set_database_preference

        if not self._session:
            return

        if hasattr(self, "_clear_query_target_database"):
            self._clear_query_target_database()

        try:
            self._session.switch_database(db_name)

            # Update app state to match session
            self.current_config = self._session.config
            self.current_connection = self._session.connection

            # Save preference and update UI
            set_database_preference(self._session.config.name, db_name)
            self.notify(f"Switched to database: {db_name}")
            self._update_status_bar()
            self._update_database_labels()

            # Clear caches and reload schema for autocomplete
            self._db_object_cache = {}
            self._load_schema_cache()

        except Exception as e:
            self.notify(f"Failed to connect to {db_name}: {e}", severity="error")

    def set_default_database(self: AppProtocol, db_name: str | None) -> None:
        """Set or clear the active database for the current connection.

        This is the shared function used by both the USE query handler and
        the explorer 'Use as default' action.

        For databases that support cross-database queries (SQL Server, MySQL, etc.),
        this just sets _active_database so queries use the right context.

        For databases that don't support cross-database queries (PostgreSQL, etc.),
        this will reconnect to the selected database since each connection is
        database-specific.

        Args:
            db_name: The database name to set as active, or None to clear.
        """
        from dataclasses import replace

        from ...config import set_database_preference

        if not self.current_config or not self.current_adapter:
            self.notify("Not connected", severity="error")
            return

        if hasattr(self, "_clear_query_target_database"):
            self._clear_query_target_database()

        # Check if adapter supports cross-database queries
        if not self.current_adapter.supports_cross_database_queries and db_name:
            # For PostgreSQL, CockroachDB, etc. - need to reconnect to the new database
            # Check if we're already connected to this database
            current_db = self.current_config.database
            if current_db and current_db.lower() == db_name.lower():
                # Already connected to this database, just update UI
                self._active_database = db_name
                self._update_status_bar()
                self._update_database_labels()
                return

            # Reconnect to the new database without re-rendering the tree
            self._reconnect_to_database(db_name)
            return

        # For databases that support cross-database queries, just update the active database
        self._active_database = db_name
        # Cache the preference so it persists across sessions
        set_database_preference(self.current_config.name, db_name)
        if db_name:
            self.notify(f"Switched to database: {db_name}")
        else:
            self.notify("Cleared default database")
        self._update_status_bar()
        self._update_database_labels()
        # Reload schema cache for autocomplete with new database context
        self._load_schema_cache()

    def _update_database_labels(self: AppProtocol) -> None:
        """Update database node labels to show the active database with a star."""
        if not self.current_config or not self.current_adapter:
            return

        active_db = None
        if hasattr(self, "_get_effective_database"):
            active_db = self._get_effective_database()

        # Find the Databases folder and update labels
        for conn_node in self.object_tree.root.children:
            if self._get_node_kind(conn_node) != "connection":
                continue

            # Check if this is the active connection
            if not (conn_node.data and conn_node.data.config.name == self.current_config.name):
                continue

            # Find Databases folder
            for child in conn_node.children:
                if self._get_node_kind(child) == "folder" and child.data.folder_type == "databases":
                    # Update each database node
                    for db_node in child.children:
                        if self._get_node_kind(db_node) == "database":
                            db_name = db_node.data.name
                            is_active = active_db and db_name.lower() == active_db.lower()
                            if is_active:
                                db_node.set_label(f"[#4ADE80]* {escape_markup(db_name)}[/]")
                            else:
                                db_node.set_label(escape_markup(db_name))
                    break
            break

    def action_use_database(self: AppProtocol) -> None:
        """Toggle the selected database as the default for the current connection."""
        node = self.object_tree.cursor_node

        if not node or self._get_node_kind(node) != "database":
            return

        if not self.current_connection or not self.current_config:
            self.notify("Not connected", severity="error")
            return

        db_name = node.data.name
        current_active = None
        if hasattr(self, "_get_effective_database"):
            current_active = self._get_effective_database()

        # Toggle: if already active, clear it; otherwise set it
        if current_active and current_active.lower() == db_name.lower():
            self.set_default_database(None)
        else:
            self.set_default_database(db_name)
