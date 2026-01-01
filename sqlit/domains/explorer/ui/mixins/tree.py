"""Tree/Explorer mixin for SSMSTUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.markup import escape as escape_markup
from textual.widgets import Tree

from sqlit.domains.connections.providers.metadata import get_connection_display_info
from sqlit.domains.explorer.domain.tree_nodes import (
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
from sqlit.shared.ui.protocols import TreeMixinHost

from .tree_labels import TreeLabelMixin
from .tree_schema import TreeSchemaMixin

if TYPE_CHECKING:
    from sqlit.domains.connections.app.session import ConnectionSession
    from sqlit.domains.connections.domain.config import ConnectionConfig
    from sqlit.domains.connections.providers.model import DatabaseProvider


class TreeMixin(TreeSchemaMixin, TreeLabelMixin):
    """Mixin providing tree/explorer functionality."""

    _active_database: str | None = None
    connections: list[ConnectionConfig]
    current_config: ConnectionConfig | None = None
    current_connection: Any | None = None
    current_provider: DatabaseProvider | None = None
    _session: ConnectionSession | None = None
    _last_query_table: dict[str, Any] | None = None
    _schema_service: Any | None = None
    _schema_service_session: Any | None = None

    def _update_connecting_indicator(self: TreeMixinHost) -> None:
        connecting_config = getattr(self, "_connecting_config", None)
        if not connecting_config:
            return

        spinner = self._connect_spinner_frame()
        label = self._format_connection_label(connecting_config, "connecting", spinner=spinner)

        for node in self.object_tree.root.children:
            if self._get_node_kind(node) != "connection":
                continue
            data = getattr(node, "data", None)
            config = getattr(data, "config", None)
            if config and config.name == connecting_config.name:
                node.set_label(label)
                node.allow_expand = False
                break

    def refresh_tree(self: TreeMixinHost) -> None:
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
        if direct_active and self.current_config is not None:
            connections: list[ConnectionConfig] = [self.current_config]
        else:
            connections = list(self.connections)
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

    def populate_connected_tree(self: TreeMixinHost) -> None:
        """Populate tree with database objects when connected."""
        if not self.current_connection or not self.current_config or not self.current_provider:
            return

        provider = self.current_provider
        schema_service = self._get_schema_service()

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
                data = getattr(child, "data", None)
                config = getattr(data, "config", None)
                if config and config.name == self.current_config.name:
                    child.set_label(get_conn_label(self.current_config, connected=True))
                    active_node = child
                    break

        if not active_node:
            active_node = self.object_tree.root.add(get_conn_label(self.current_config, connected=True))
            active_node.data = ConnectionNode(config=self.current_config)
            active_node.allow_expand = True

        active_node.remove_children()

        try:
            if provider.capabilities.supports_multiple_databases:
                endpoint = self.current_config.tcp_endpoint
                specific_db = endpoint.database if endpoint else ""
                # Show a single database view when a specific database was configured.
                # Otherwise, show the Databases folder to browse all databases.
                show_single_db = specific_db and specific_db.lower() not in ("", "master")
                if show_single_db:
                    self._add_database_object_nodes(active_node, specific_db)
                    active_node.expand()
                else:
                    dbs_node = active_node.add("Databases")
                    dbs_node.data = FolderNode(folder_type="databases")

                    if not schema_service:
                        databases = []
                    else:
                        databases = schema_service.list_databases()
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

    def _add_database_object_nodes(self: TreeMixinHost, parent_node: Any, database: str | None) -> None:
        """Add Tables, Views, Indexes, Triggers, Sequences, and Stored Procedures nodes."""
        if not self.current_provider:
            return

        caps = self.current_provider.capabilities
        node_provider = self.current_provider.explorer_nodes

        for folder in node_provider.get_root_folders(caps):
            if folder.requires(caps):
                folder_node = parent_node.add(folder.label)
                folder_node.data = FolderNode(folder_type=folder.kind, database=database)
                folder_node.allow_expand = True
            else:
                parent_node.add_leaf(f"[dim]{folder.label} (Not available)[/]")

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

    def _restore_subtree_expansion(self: TreeMixinHost, node: Any) -> None:
        """Recursively expand nodes that should be expanded."""
        for child in node.children:
            if child.data:
                path = self._get_node_path(child)
                if path in self._expanded_paths:
                    child.expand()
            self._restore_subtree_expansion(child)

    def _save_expanded_state(self: TreeMixinHost) -> None:
        """Save which nodes are expanded."""
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
        settings = self.services.settings_store.load_all()
        settings["expanded_nodes"] = expanded
        self.services.settings_store.save_all(settings)

    def on_tree_node_collapsed(self: TreeMixinHost, event: Tree.NodeCollapsed) -> None:
        """Save state when a node is collapsed."""
        self.call_later(self._save_expanded_state)

    def on_tree_node_expanded(self: TreeMixinHost, event: Tree.NodeExpanded) -> None:
        """Load child objects when a node is expanded."""
        node = event.node

        self.call_later(self._save_expanded_state)

        if not node.data or not self.current_connection or not self.current_provider:
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

    def _load_columns_async(self: TreeMixinHost, node: Any, data: TableNode | ViewNode) -> None:
        """Spawn worker to load columns for a table/view."""
        db_name = data.database
        schema_name = data.schema
        obj_name = data.name

        def work() -> None:
            """Run in worker thread."""
            try:
                schema_service = self._get_schema_service()
                if not schema_service:
                    columns = []
                else:
                    columns = schema_service.list_columns(db_name, schema_name, obj_name)

                # Update UI from worker thread
                self.call_from_thread(self._on_columns_loaded, node, db_name, schema_name, obj_name, columns)
            except Exception as e:
                self.call_from_thread(self._on_tree_load_error, node, f"Error loading columns: {e}")

        self.run_worker(work, name=f"load-columns-{obj_name}", thread=True, exclusive=False)

    def _on_columns_loaded(
        self: TreeMixinHost, node: Any, db_name: str | None, schema_name: str, obj_name: str, columns: list
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

    def _load_folder_async(self: TreeMixinHost, node: Any, data: FolderNode) -> None:
        """Spawn worker to load folder contents (tables/views/indexes/triggers/sequences/procedures)."""
        folder_type = data.folder_type
        db_name = data.database

        def work() -> None:
            """Run in worker thread."""
            try:
                schema_service = self._get_schema_service()
                if not schema_service:
                    items = []
                else:
                    items = schema_service.list_folder_items(folder_type, db_name)

                # Update UI from worker thread
                self.call_from_thread(self._on_folder_loaded, node, db_name, folder_type, items)
            except Exception as e:
                # If we have a target database, try reconnecting as fallback (handles Azure SQL etc.)
                if db_name:
                    self.call_from_thread(self._fallback_reconnect_and_retry, node, data, db_name, e)
                else:
                    self.call_from_thread(self._on_tree_load_error, node, f"Error loading: {e}")

        self.run_worker(work, name=f"load-folder-{folder_type}", thread=True, exclusive=False)

    def _on_folder_loaded(self: TreeMixinHost, node: Any, db_name: str | None, folder_type: str, items: list) -> None:
        """Handle folder load completion on main thread."""
        node_path = self._get_node_path(node)
        self._loading_nodes.discard(node_path)

        for child in list(node.children):
            if self._get_node_kind(child) == "loading":
                child.remove()

        if not self._session:
            return

        provider = self._session.provider
        if not items:
            empty_child = node.add_leaf("[dim](Empty)[/]")
            empty_child.data = LoadingNode()
            return

        if folder_type in ("tables", "views"):
            self._add_schema_grouped_items(
                node,
                db_name,
                folder_type,
                items,
                provider.capabilities.default_schema,
            )
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

    def _on_tree_load_error(self: TreeMixinHost, node: Any, error_message: str) -> None:
        """Handle tree load error on main thread."""
        node_path = self._get_node_path(node)
        self._loading_nodes.discard(node_path)

        for child in list(node.children):
            if self._get_node_kind(child) == "loading":
                child.remove()

        self.notify(escape_markup(error_message), severity="error")

    def _fallback_reconnect_and_retry(
        self: TreeMixinHost, node: Any, data: FolderNode, db_name: str, original_error: Exception
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

    def on_tree_node_selected(self: TreeMixinHost, event: Tree.NodeSelected) -> None:
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

    def on_tree_node_highlighted(self: TreeMixinHost, event: Tree.NodeHighlighted) -> None:
        """Update footer when tree selection changes."""
        self._update_footer_bindings()

    def action_refresh_tree(self: TreeMixinHost) -> None:
        """Refresh the explorer."""
        # Clear shared object cache so fresh data is fetched
        self._get_object_cache().clear()
        # Clear column cache too so columns are re-fetched
        if hasattr(self, "_schema_cache") and "columns" in self._schema_cache:
            self._schema_cache["columns"] = {}
        # Clear loading nodes set to allow re-loading
        if hasattr(self, "_loading_nodes"):
            self._loading_nodes.clear()
        # Force schema service to be recreated on next access
        self._schema_service = None
        self.refresh_tree()
        # Reload autocomplete schema cache
        if hasattr(self, "_load_schema_cache"):
            self._load_schema_cache()
        self.notify("Refreshed")

    def action_collapse_tree(self: TreeMixinHost) -> None:
        """Collapse all nodes in the explorer."""

        def collapse_all(node: Any) -> None:
            for child in node.children:
                collapse_all(child)
                child.collapse()

        collapse_all(self.object_tree.root)
        self._expanded_paths.clear()
        self._save_expanded_state()

    def action_tree_cursor_down(self: TreeMixinHost) -> None:
        """Move tree cursor down (vim j)."""
        if self.object_tree.has_focus:
            self.object_tree.action_cursor_down()

    def action_tree_cursor_up(self: TreeMixinHost) -> None:
        """Move tree cursor up (vim k)."""
        if self.object_tree.has_focus:
            self.object_tree.action_cursor_up()

    def action_select_table(self: TreeMixinHost) -> None:
        """Generate and execute SELECT query for selected table/view, or show info for indexes/triggers/sequences."""
        if not self.current_provider or not self._session:
            return

        node = self.object_tree.cursor_node

        if not node or not node.data:
            return

        data = node.data

        # Handle table/view - execute SELECT query
        if self._get_node_kind(node) in ("table", "view"):
            # Store table info for edit_cell action
            try:
                schema_service = self._get_schema_service()
                columns = schema_service.list_columns(data.database, data.schema, data.name) if schema_service else []
                self._last_query_table = {
                    "database": data.database,
                    "schema": data.schema,
                    "name": data.name,
                    "columns": columns,
                }
            except Exception:
                self._last_query_table = None

            self.query_input.text = self.current_provider.dialect.build_select_query(
                data.name,
                100,
                data.database,
                data.schema,
            )
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

    def _show_index_info(self: TreeMixinHost, data: IndexNode) -> None:
        """Show index definition in the results panel."""
        schema_service = self._get_schema_service()
        if not schema_service:
            return

        try:
            info = schema_service.get_index_definition(data.database, data.name, data.table_name)
            if info is None:
                self.notify("Indexes not supported for this database.", severity="warning")
                return
            self._display_object_info("Index", info)
        except Exception as e:
            self.notify(f"Error getting index info: {e}", severity="error")

    def _show_trigger_info(self: TreeMixinHost, data: TriggerNode) -> None:
        """Show trigger definition in the results panel."""
        schema_service = self._get_schema_service()
        if not schema_service:
            return

        try:
            info = schema_service.get_trigger_definition(data.database, data.name, data.table_name)
            if info is None:
                self.notify("Triggers not supported for this database.", severity="warning")
                return
            self._display_object_info("Trigger", info)
        except Exception as e:
            self.notify(f"Error getting trigger info: {e}", severity="error")

    def _show_sequence_info(self: TreeMixinHost, data: SequenceNode) -> None:
        """Show sequence information in the results panel."""
        schema_service = self._get_schema_service()
        if not schema_service:
            return

        try:
            info = schema_service.get_sequence_definition(data.database, data.name)
            if info is None:
                self.notify("Sequences not supported for this database.", severity="warning")
                return
            self._display_object_info("Sequence", info)
        except Exception as e:
            self.notify(f"Error getting sequence info: {e}", severity="error")

    def _display_object_info(self: TreeMixinHost, object_type: str, info: dict) -> None:
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
        self._replace_results_table(["Property", "Value"], rows)

        # Store for copy/export functionality
        self._last_result_columns = ["Property", "Value"]
        self._last_result_rows = rows
        self._last_result_row_count = len(rows)

        self.notify(f"{object_type}: {info.get('name', 'Unknown')}")

        # Also show the definition in the query input if available
        definition = info.get("definition")
        if definition:
            self.query_input.text = f"/*\n{definition}\n*/"

    def _ensure_database_connection(self: TreeMixinHost, target_db: str) -> bool:
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
        if not self.current_provider or not self.current_config:
            return False

        # For cross-db adapters, try USE approach first (no reconnection needed).
        # Note: While MSSQL generally supports cross-database queries, some variants
        # like Azure SQL have restrictions. If USE fails, we fall back to reconnection.
        if self.current_provider.capabilities.supports_cross_database_queries:
            current_active = getattr(self, "_active_database", None)
            if not current_active or current_active.lower() != target_db.lower():
                try:
                    self.set_default_database(target_db)
                except Exception:
                    # USE approach failed - fall back to reconnection
                    self._reconnect_to_database(target_db)
            return True

        # For non-cross-db adapters, check if already connected to target database
        endpoint = self.current_config.tcp_endpoint
        current_db = endpoint.database if endpoint else ""
        if current_db and current_db.lower() == target_db.lower():
            return True

        # Need to reconnect - set_default_database handles this
        self.set_default_database(target_db)

        # Verify switch succeeded
        endpoint = self.current_config.tcp_endpoint
        return bool(endpoint and endpoint.database and endpoint.database.lower() == target_db.lower())

    def _reconnect_to_database(self: TreeMixinHost, db_name: str) -> None:
        """Reconnect to a different database without re-rendering the tree.

        Used for PostgreSQL and other databases that don't support cross-database
        queries. Creates a new connection to the specified database while keeping
        the tree structure intact.
        """
        if not self._session:
            return

        if hasattr(self, "_clear_query_target_database"):
            self._clear_query_target_database()

        try:
            self._session.switch_database(db_name)

            # Update app state to match session
            self.current_config = self._session.config
            self.current_connection = self._session.connection

            # Update UI
            self.notify(f"Switched to database: {db_name}")
            self._update_status_bar()
            self._update_database_labels()

            # Clear caches and reload schema for autocomplete
            self._get_object_cache().clear()
            self._load_schema_cache()

        except Exception as e:
            self.notify(f"Failed to connect to {db_name}: {e}", severity="error")

    def set_default_database(self: TreeMixinHost, db_name: str | None) -> None:
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
        if not self.current_config or not self.current_provider:
            self.notify("Not connected", severity="error")
            return

        if hasattr(self, "_clear_query_target_database"):
            self._clear_query_target_database()

        # Check if adapter supports cross-database queries
        if not self.current_provider.capabilities.supports_cross_database_queries and db_name:
            # For PostgreSQL, CockroachDB, etc. - need to reconnect to the new database
            # Check if we're already connected to this database
            endpoint = self.current_config.tcp_endpoint
            current_db = endpoint.database if endpoint else ""
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
        if db_name:
            self.notify(f"Switched to database: {db_name}")
        else:
            self.notify("Cleared default database")
        self._update_status_bar()
        self._update_database_labels()
        # Reload schema cache for autocomplete with new database context
        self._load_schema_cache()

    def _update_database_labels(self: TreeMixinHost) -> None:
        """Update database node labels to show the active database with a star."""
        if not self.current_config or not self.current_provider:
            return

        active_db = None
        if hasattr(self, "_get_effective_database"):
            active_db = self._get_effective_database()

        # Find the Databases folder and update labels
        for conn_node in self.object_tree.root.children:
            if self._get_node_kind(conn_node) != "connection":
                continue

            # Check if this is the active connection
            conn_data = getattr(conn_node, "data", None)
            conn_config = getattr(conn_data, "config", None)
            if not (conn_config and conn_config.name == self.current_config.name):
                continue

            # Find Databases folder
            for child in conn_node.children:
                child_data = getattr(child, "data", None)
                folder_type = getattr(child_data, "folder_type", None)
                if self._get_node_kind(child) == "folder" and folder_type == "databases":
                    # Update each database node
                    for db_node in child.children:
                        if self._get_node_kind(db_node) == "database":
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
            break

    def action_use_database(self: TreeMixinHost) -> None:
        """Toggle the selected database as the default for the current connection."""
        node = self.object_tree.cursor_node

        if not node or self._get_node_kind(node) != "database":
            return

        if not self.current_connection or not self.current_config:
            self.notify("Not connected", severity="error")
            return

        data = getattr(node, "data", None)
        db_name = getattr(data, "name", None)
        if not db_name:
            return
        current_active = None
        if hasattr(self, "_get_effective_database"):
            current_active = self._get_effective_database()

        # Toggle: if already active, clear it; otherwise set it
        if current_active and current_active.lower() == db_name.lower():
            self.set_default_database(None)
        else:
            self.set_default_database(db_name)
