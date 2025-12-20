"""Tree/Explorer mixin for SSMSTUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.markup import escape as escape_markup
from textual.widgets import Tree

from ..protocols import AppProtocol
from .query import SPINNER_FRAMES
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

    def _db_type_badge(self, db_type: str) -> str:
        """Get short badge for database type."""
        badge_map = {
            "mssql": "MSSQL",
            "postgresql": "PG",
            "mysql": "MySQL",
            "mariadb": "MariaDB",
            "sqlite": "SQLite",
            "oracle": "Oracle",
            "duckdb": "DuckDB",
            "cockroachdb": "CRDB",
            "turso": "Turso",
        }
        return badge_map.get(db_type, db_type.upper() if db_type else "DB")

    def _format_connection_label(self, conn: Any, status: str, spinner: str | None = None) -> str:
        display_info = escape_markup(conn.get_display_info())
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

    def _update_connecting_indicator(self: AppProtocol) -> None:
        connecting_config = getattr(self, "_connecting_config", None)
        if not connecting_config:
            return

        spinner = self._connect_spinner_frame()
        label = self._format_connection_label(connecting_config, "connecting", spinner=spinner)

        for node in self.object_tree.root.children:
            if isinstance(node.data, ConnectionNode) and node.data.config.name == connecting_config.name:
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
            display_info = escape_markup(config.get_display_info())
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
            if isinstance(child.data, ConnectionNode):
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
                if specific_db and specific_db.lower() not in ("", "master"):
                    self._add_database_object_nodes(active_node, specific_db)
                    active_node.expand()
                else:
                    dbs_node = active_node.add("Databases")
                    dbs_node.data = FolderNode(folder_type="databases")

                    databases = adapter.get_databases(self.current_connection)
                    for db_name in databases:
                        db_node = dbs_node.add(escape_markup(db_name))
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
            if isinstance(data, ConnectionNode):
                parts.append(f"conn:{data.config.name}")
            elif isinstance(data, DatabaseNode):
                parts.append(f"db:{data.name}")
            elif isinstance(data, FolderNode):
                parts.append(f"folder:{data.folder_type}")
            elif isinstance(data, SchemaNode):
                parts.append(f"schema:{data.schema}")
            elif isinstance(data, TableNode | ViewNode):
                node_type = "table" if isinstance(data, TableNode) else "view"
                parts.append(f"{node_type}:{data.schema}.{data.name}")
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

        # Skip if already has children (not just loading placeholder)
        children = list(node.children)
        if children:
            # Check if it's just a loading placeholder
            if len(children) == 1 and isinstance(children[0].data, LoadingNode):
                return  # Already loading
            if not isinstance(children[0].data, LoadingNode):
                return  # Already loaded

        # Initialize _loading_nodes if not present
        if not hasattr(self, "_loading_nodes") or self._loading_nodes is None:
            self._loading_nodes = set()

        # Get node path to track loading state
        node_path = self._get_node_path(node)
        if node_path in self._loading_nodes:
            return  # Already loading this node

        # Handle table/view column expansion
        if isinstance(data, TableNode | ViewNode):
            self._loading_nodes.add(node_path)
            loading_node = node.add_leaf("[dim italic]Loading...[/]")
            loading_node.data = LoadingNode()
            self._load_columns_async(node, data)
            return

        # Handle folder expansion (database can be None for single-db adapters)
        if isinstance(data, FolderNode):
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
                    columns = adapter.get_columns(conn, obj_name, db_name, schema_name)

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
            if isinstance(child.data, LoadingNode):
                child.remove()

        for col in columns:
            col_name = escape_markup(col.name)
            col_type = escape_markup(col.data_type)
            child = node.add_leaf(f"[dim]{col_name}[/] [italic dim]{col_type}[/]")
            child.data = ColumnNode(database=db_name, schema=schema_name, table=obj_name, name=col.name)

    def _load_folder_async(self: AppProtocol, node: Any, data: FolderNode) -> None:
        """Spawn worker to load folder contents (tables/views/indexes/triggers/sequences/procedures)."""
        folder_type = data.folder_type
        db_name = data.database

        def work() -> None:
            """Run in worker thread."""
            try:
                if not self._session:
                    items = []
                else:
                    adapter = self._session.adapter
                    conn = self._session.connection

                    if folder_type == "tables":
                        items = [("table", s, t) for s, t in adapter.get_tables(conn, db_name)]
                    elif folder_type == "views":
                        items = [("view", s, v) for s, v in adapter.get_views(conn, db_name)]
                    elif folder_type == "indexes":
                        if adapter.supports_indexes:
                            items = [("index", i.name, i.table_name) for i in adapter.get_indexes(conn, db_name)]
                        else:
                            items = []
                    elif folder_type == "triggers":
                        if adapter.supports_triggers:
                            items = [("trigger", t.name, t.table_name) for t in adapter.get_triggers(conn, db_name)]
                        else:
                            items = []
                    elif folder_type == "sequences":
                        if adapter.supports_sequences:
                            items = [("sequence", s.name, "") for s in adapter.get_sequences(conn, db_name)]
                        else:
                            items = []
                    elif folder_type == "procedures":
                        if adapter.supports_stored_procedures:
                            items = [("procedure", "", p) for p in adapter.get_procedures(conn, db_name)]
                        else:
                            items = []
                    else:
                        items = []

                # Update UI from worker thread
                self.call_from_thread(self._on_folder_loaded, node, db_name, folder_type, items)
            except Exception as e:
                self.call_from_thread(self._on_tree_load_error, node, f"Error loading: {e}")

        self.run_worker(work, name=f"load-folder-{folder_type}", thread=True, exclusive=False)

    def _on_folder_loaded(self: AppProtocol, node: Any, db_name: str | None, folder_type: str, items: list) -> None:
        """Handle folder load completion on main thread."""
        node_path = self._get_node_path(node)
        self._loading_nodes.discard(node_path)

        for child in list(node.children):
            if isinstance(child.data, LoadingNode):
                child.remove()

        if not self._session:
            return

        adapter = self._session.adapter

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
            if isinstance(child.data, LoadingNode):
                child.remove()

        self.notify(escape_markup(error_message), severity="error")

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

        if isinstance(data, ConnectionNode):
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
        if isinstance(data, TableNode | ViewNode):
            # Store table info for edit_cell action
            try:
                columns = self._session.adapter.get_columns(
                    self._session.connection, data.name, data.database, data.schema
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
            self.action_execute_query()
            return

        # Handle index - show index definition
        if isinstance(data, IndexNode):
            self._show_index_info(data)
            return

        # Handle trigger - show trigger definition
        if isinstance(data, TriggerNode):
            self._show_trigger_info(data)
            return

        # Handle sequence - show sequence info
        if isinstance(data, SequenceNode):
            self._show_sequence_info(data)
            return

    def _show_index_info(self: AppProtocol, data: IndexNode) -> None:
        """Show index definition in the results panel."""
        if not self._session:
            return

        try:
            info = self._session.adapter.get_index_definition(
                self._session.connection, data.name, data.table_name, data.database
            )
            self._display_object_info("Index", info)
        except Exception as e:
            self.notify(f"Error getting index info: {e}", severity="error")

    def _show_trigger_info(self: AppProtocol, data: TriggerNode) -> None:
        """Show trigger definition in the results panel."""
        if not self._session:
            return

        try:
            info = self._session.adapter.get_trigger_definition(
                self._session.connection, data.name, data.table_name, data.database
            )
            self._display_object_info("Trigger", info)
        except Exception as e:
            self.notify(f"Error getting trigger info: {e}", severity="error")

    def _show_sequence_info(self: AppProtocol, data: SequenceNode) -> None:
        """Show sequence information in the results panel."""
        if not self._session:
            return

        try:
            info = self._session.adapter.get_sequence_definition(
                self._session.connection, data.name, data.database
            )
            self._display_object_info("Sequence", info)
        except Exception as e:
            self.notify(f"Error getting sequence info: {e}", severity="error")

    def _display_object_info(self: AppProtocol, object_type: str, info: dict) -> None:
        """Display object info in the results table as a Property/Value view."""
        # Build rows for display
        rows = []
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

        # Update the results table
        self.results_table.clear(columns=True)
        self.results_table.show_header = True
        self.results_table.add_columns("Property", "Value")

        for prop, val in rows:
            self.results_table.add_row(escape_markup(prop), escape_markup(val))

        # Store for copy/export functionality
        self._last_result_columns = ["Property", "Value"]
        self._last_result_rows = rows
        self._last_result_row_count = len(rows)

        self.notify(f"{object_type}: {info.get('name', 'Unknown')}")

        # Also show the definition in the query input if available
        definition = info.get("definition")
        if definition:
            self.query_input.text = f"/*\n{definition}\n*/"
