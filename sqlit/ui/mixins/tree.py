"""Tree/Explorer mixin for SSMSTUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.markup import escape as escape_markup
from textual.widgets import Tree

from ..protocols import AppProtocol
from ..tree_nodes import (
    ColumnNode,
    ConnectionNode,
    DatabaseNode,
    FolderNode,
    LoadingNode,
    ProcedureNode,
    SchemaNode,
    TableNode,
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

    def refresh_tree(self: AppProtocol) -> None:
        """Refresh the explorer tree."""
        self.object_tree.clear()
        self.object_tree.root.expand()

        for conn in self.connections:
            display_info = escape_markup(conn.get_display_info())
            db_type_label = self._db_type_badge(conn.db_type)
            escaped_name = escape_markup(conn.name)
            # Check if this is the connected server
            is_connected = (
                self.current_config is not None
                and conn.name == self.current_config.name
            )
            if is_connected:
                label = f"[green]* {escaped_name}[/green] [{db_type_label}] ({display_info})"
            else:
                label = f"[dim]{escaped_name}[/dim] [{db_type_label}] ({display_info})"
            node = self.object_tree.root.add(label)
            node.data = ConnectionNode(config=conn)
            node.allow_expand = True

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
            if connected:
                name = f"[green]* {escaped_name}[/green]"
            else:
                name = escaped_name
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
        """Add Tables, Views, and optionally Stored Procedures nodes."""
        tables_node = parent_node.add("Tables")
        tables_node.data = FolderNode(folder_type="tables", database=database)
        tables_node.allow_expand = True

        views_node = parent_node.add("Views")
        views_node.data = FolderNode(folder_type="views", database=database)
        views_node.allow_expand = True

        if self.current_adapter and self.current_adapter.supports_stored_procedures:
            procs_node = parent_node.add("Stored Procedures")
            procs_node.data = FolderNode(folder_type="procedures", database=database)
            procs_node.allow_expand = True

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
        """Spawn worker to load folder contents (tables/views/procedures)."""
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
                    child = node.add(escape_markup(item[2]))
                    child.data = ProcedureNode(database=db_name, name=item[2])

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
        node = event.node
        if not node.data:
            return

        data = node.data

        if isinstance(data, ConnectionNode):
            config = data.config
            if self.current_config and self.current_config.name == config.name:
                return
            if self.current_connection:
                self._disconnect_silent()
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

    def action_select_table(self: AppProtocol) -> None:
        """Generate and execute SELECT query for selected table/view."""
        if not self.current_adapter:
            return

        node = self.object_tree.cursor_node

        if not node or not node.data:
            return

        data = node.data
        if not isinstance(data, TableNode | ViewNode):
            return

        self.query_input.text = self.current_adapter.build_select_query(data.name, 100, data.database, data.schema)
        self.action_execute_query()
