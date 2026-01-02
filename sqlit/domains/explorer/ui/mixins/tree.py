"""Tree/Explorer mixin for SSMSTUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.widgets import Tree

from sqlit.shared.ui.protocols import TreeMixinHost

from ..tree import builder as tree_builder
from ..tree import db_switching as tree_db_switching
from ..tree import expansion_state as tree_expansion_state
from ..tree import loaders as tree_loaders
from ..tree import object_info as tree_object_info
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

    def on_tree_node_collapsed(self: TreeMixinHost, event: Tree.NodeCollapsed) -> None:
        """Save state when a node is collapsed."""
        self.call_later(lambda: tree_expansion_state.save_expanded_state(self))

    def on_tree_node_expanded(self: TreeMixinHost, event: Tree.NodeExpanded) -> None:
        """Load child objects when a node is expanded."""
        node = event.node

        self.call_later(lambda: tree_expansion_state.save_expanded_state(self))

        if not node.data or not self.current_connection or not self.current_provider:
            return

        data = node.data

        if self._get_node_kind(node) == "database":
            tree_db_switching.ensure_database_connection(self, data.name)

        children = list(node.children)
        if children:
            if len(children) == 1 and self._get_node_kind(children[0]) == "loading":
                return
            if self._get_node_kind(children[0]) != "loading":
                return

        loading_nodes = tree_loaders.ensure_loading_nodes(self)

        node_path = tree_expansion_state.get_node_path(self, node)
        if node_path in loading_nodes:
            return

        if self._get_node_kind(node) in ("table", "view"):
            target_db = data.database
            if target_db and not tree_db_switching.ensure_database_connection(self, target_db):
                return
            loading_nodes.add(node_path)
            tree_loaders.add_loading_placeholder(self, node)
            self._load_columns_async(node, data)
            return

        if self._get_node_kind(node) == "folder":
            target_db = data.database
            if target_db and not tree_db_switching.ensure_database_connection(self, target_db):
                return
            loading_nodes.add(node_path)
            tree_loaders.add_loading_placeholder(self, node)
            self._load_folder_async(node, data)
            return

    def _load_columns_async(self: TreeMixinHost, node: Any, data: Any) -> None:
        tree_loaders.load_columns_async(self, node, data)

    def _load_folder_async(self: TreeMixinHost, node: Any, data: Any) -> None:
        tree_loaders.load_folder_async(self, node, data)

    def _add_schema_grouped_items(
        self: TreeMixinHost,
        node: Any,
        db_name: str | None,
        folder_type: str,
        items: list[Any],
        default_schema: str,
    ) -> None:
        from ..tree import schema_render

        schema_render.add_schema_grouped_items(self, node, db_name, folder_type, items, default_schema)

    def _on_columns_loaded(
        self: TreeMixinHost,
        node: Any,
        db_name: str | None,
        schema_name: str,
        obj_name: str,
        columns: list[Any],
    ) -> None:
        tree_loaders.on_columns_loaded(self, node, db_name, schema_name, obj_name, columns)

    def _on_folder_loaded(
        self: TreeMixinHost,
        node: Any,
        db_name: str | None,
        folder_type: str,
        items: list[Any],
    ) -> None:
        tree_loaders.on_folder_loaded(self, node, db_name, folder_type, items)

    def _on_tree_load_error(self: TreeMixinHost, node: Any, error_message: str) -> None:
        tree_loaders.on_tree_load_error(self, node, error_message)

    def on_tree_node_selected(self: TreeMixinHost, event: Tree.NodeSelected) -> None:
        """Handle tree node selection (double-click/enter)."""
        if getattr(self, "_tree_filter_visible", False):
            return

        node = event.node
        self._activate_tree_node(node)

    def _activate_tree_node(self: TreeMixinHost, node: Any) -> None:
        """Activate a tree node (connect to server, expand folder, etc.)."""
        if not node.data:
            return

        data = node.data

        if self._get_node_kind(node) == "connection":
            config = data.config
            if self.current_config and self.current_config.name == config.name:
                return
            self.connect_to_server(config)

    def on_tree_node_highlighted(self: TreeMixinHost, event: Tree.NodeHighlighted) -> None:
        """Update footer when tree selection changes."""
        self._update_footer_bindings()

    def action_refresh_tree(self: TreeMixinHost) -> None:
        """Refresh the explorer."""
        self._get_object_cache().clear()
        if hasattr(self, "_schema_cache") and "columns" in self._schema_cache:
            self._schema_cache["columns"] = {}
        if hasattr(self, "_loading_nodes"):
            self._loading_nodes.clear()
        self._schema_service = None
        self.refresh_tree()
        if hasattr(self, "_load_schema_cache"):
            self._load_schema_cache()
        self.notify("Refreshed")

    def refresh_tree(self: TreeMixinHost) -> None:
        tree_builder.refresh_tree(self)

    def action_collapse_tree(self: TreeMixinHost) -> None:
        """Collapse all nodes in the explorer."""

        def collapse_all(node: Any) -> None:
            for child in node.children:
                collapse_all(child)
                child.collapse()

        collapse_all(self.object_tree.root)
        self._expanded_paths.clear()
        tree_expansion_state.save_expanded_state(self)

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

        if self._get_node_kind(node) in ("table", "view"):
            try:
                schema_service = self._get_schema_service()
                columns = (
                    schema_service.list_columns(data.database, data.schema, data.name)
                    if schema_service
                    else []
                )
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
            self._query_target_database = data.database
            self.action_execute_query()
            return

        if self._get_node_kind(node) == "index":
            tree_object_info.show_index_info(self, data)
            return

        if self._get_node_kind(node) == "trigger":
            tree_object_info.show_trigger_info(self, data)
            return

        if self._get_node_kind(node) == "sequence":
            tree_object_info.show_sequence_info(self, data)
            return

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

        if current_active and current_active.lower() == db_name.lower():
            tree_db_switching.set_default_database(self, None)
        else:
            tree_db_switching.set_default_database(self, db_name)
