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

MIN_TIMER_DELAY_S = 0.001


class TreeMixin(TreeSchemaMixin, TreeLabelMixin):
    """Mixin providing tree/explorer functionality."""

    _active_database: str | None = None
    connections: list[ConnectionConfig]
    current_config: ConnectionConfig | None = None
    current_connection: Any | None = None
    current_provider: DatabaseProvider | None = None
    _session: ConnectionSession | None = None
    _last_query_table: dict[str, Any] | None = None
    _last_query_table_token: int = 0
    _db_switch_token: int = 0
    _expanded_state_save_timer: Any | None = None
    _schema_service: Any | None = None
    _schema_service_session: Any | None = None

    def _emit_debug(self: TreeMixinHost, name: str, **data: Any) -> None:
        emit = getattr(self, "emit_debug_event", None)
        if callable(emit):
            emit(name, **data)

    def _schedule_timer(self: TreeMixinHost, delay_s: float, callback: Any) -> Any | None:
        set_timer = getattr(self, "set_timer", None)
        if callable(set_timer):
            return set_timer(delay_s, callback)
        call_later = getattr(self, "call_later", None)
        if callable(call_later):
            try:
                call_later(callback)
                return None
            except Exception:
                pass
        try:
            callback()
        except Exception:
            pass
        return None

    def on_tree_node_collapsed(self: TreeMixinHost, event: Tree.NodeCollapsed) -> None:
        """Save state when a node is collapsed."""
        tree_expansion_state.update_expanded_state(self, event.node, expanded=False)
        self._schedule_expanded_state_persist()

    def on_tree_node_expanded(self: TreeMixinHost, event: Tree.NodeExpanded) -> None:
        """Load child objects when a node is expanded."""
        node = event.node

        tree_expansion_state.update_expanded_state(self, node, expanded=True)
        self._schedule_expanded_state_persist()

        if not node.data or self.current_connection is None or self.current_provider is None:
            return

        data = node.data

        if self._get_node_kind(node) == "database":
            self._ensure_database_connection_async(data.name)

        if self._get_node_kind(node) == "connection":
            config = getattr(data, "config", None)
            if (
                config
                and self.current_config
                and self.current_config.name == config.name
                and not list(node.children)
            ):
                tree_builder.populate_connected_tree(self)
            return

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

            def _continue() -> None:
                if node_path in loading_nodes:
                    return
                loading_nodes.add(node_path)
                tree_loaders.add_loading_placeholder(self, node)
                self._load_columns_async(node, data)

            if target_db:
                self._ensure_database_connection_async(target_db, _continue)
            else:
                _continue()
            return

        if self._get_node_kind(node) == "folder":
            target_db = data.database

            def _continue() -> None:
                if node_path in loading_nodes:
                    return
                loading_nodes.add(node_path)
                tree_loaders.add_loading_placeholder(self, node)
                self._load_folder_async(node, data)

            if target_db:
                self._ensure_database_connection_async(target_db, _continue)
            else:
                _continue()
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
            self._emit_debug(
                "tree.connection_selected",
                connection=config.name,
                current_connection=getattr(self.current_config, "name", None),
            )
            if self.current_config and self.current_config.name == config.name:
                return
            self.connect_to_server(config)

    def on_tree_node_highlighted(self: TreeMixinHost, event: Tree.NodeHighlighted) -> None:
        """Update footer when tree selection changes."""
        self._update_footer_bindings()

    def action_refresh_tree(self: TreeMixinHost) -> None:
        """Refresh the explorer."""
        self._refresh_tree_common(notify=True)

    def _refresh_tree_after_schema_change(self: TreeMixinHost) -> None:
        """Refresh tree after DDL without showing a notification."""
        self._refresh_tree_common(notify=False)

    def _refresh_tree_common(self: TreeMixinHost, *, notify: bool) -> None:
        self._get_object_cache().clear()
        if hasattr(self, "_schema_cache") and isinstance(self._schema_cache, dict):
            self._schema_cache["columns"] = {}
            self._schema_cache["tables"] = []
            self._schema_cache["views"] = []
            self._schema_cache["procedures"] = []
        if hasattr(self, "_db_object_cache"):
            self._db_object_cache = {}
        if hasattr(self, "_loading_nodes"):
            self._loading_nodes.clear()
        self._schema_service = None

        # Reload saved connections from disk (in case added via CLI)
        try:
            services = getattr(self, "services", None)
            if services:
                store = getattr(services, "connection_store", None)
                if store:
                    reloaded = store.load_all(load_credentials=False)
                    self.connections = reloaded
        except Exception:
            pass  # Keep existing connections if reload fails

        self.refresh_tree()
        loader = getattr(self, "_load_schema_cache", None)
        if callable(loader):
            request_token = object()
            setattr(self, "_schema_load_request_token", request_token)

            def run_loader() -> None:
                if getattr(self, "_schema_load_request_token", None) is not request_token:
                    return
                loader()

            try:
                from sqlit.domains.shell.app.idle_scheduler import Priority, get_idle_scheduler
            except Exception:
                scheduler = None
            else:
                scheduler = get_idle_scheduler()
            if scheduler:
                scheduler.request_idle_callback(
                    run_loader,
                    priority=Priority.LOW,
                    name="schema-load",
                )
            else:
                self._schedule_timer(MIN_TIMER_DELAY_S, run_loader)
        if notify:
            self.notify("Refreshed")

    def refresh_tree(self: TreeMixinHost) -> None:
        tree_builder.refresh_tree_chunked(self)

    def action_collapse_tree(self: TreeMixinHost) -> None:
        """Collapse all nodes in the explorer."""

        def collapse_all(node: Any) -> None:
            for child in node.children:
                collapse_all(child)
                child.collapse()

        collapse_all(self.object_tree.root)
        self._expanded_paths.clear()
        self._schedule_expanded_state_persist()

    def action_tree_cursor_down(self: TreeMixinHost) -> None:
        """Move tree cursor down (vim j)."""
        if self.object_tree.has_focus:
            self.object_tree.action_cursor_down()
            # Update visual selection if in visual mode
            update_visual = getattr(self, "_update_visual_selection", None)
            if callable(update_visual):
                update_visual()

    def action_tree_cursor_up(self: TreeMixinHost) -> None:
        """Move tree cursor up (vim k)."""
        if self.object_tree.has_focus:
            self.object_tree.action_cursor_up()
            # Update visual selection if in visual mode
            update_visual = getattr(self, "_update_visual_selection", None)
            if callable(update_visual):
                update_visual()

    def action_select_table(self: TreeMixinHost) -> None:
        """Generate and execute SELECT query for selected table/view, or show info for indexes/triggers/sequences."""
        if not self.current_provider or not self._session:
            return

        node = self.object_tree.cursor_node

        if not node or not node.data:
            return

        data = node.data

        if self._get_node_kind(node) in ("table", "view"):
            self._last_query_table = {
                "database": data.database,
                "schema": data.schema,
                "name": data.name,
                "columns": [],
            }
            # Stash per-result metadata so results can resolve PKs without relying on globals.
            self._pending_result_table_info = self._last_query_table
            self._prime_last_query_table_columns(data.database, data.schema, data.name)

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

        if self.current_connection is None or self.current_config is None:
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
            caps = self.current_provider.capabilities
            if caps.supports_cross_database_queries:
                tree_db_switching.set_default_database(self, db_name)
            else:
                self._switch_database_async(db_name)

    def _prime_last_query_table_columns(
        self: TreeMixinHost,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> None:
        self._last_query_table_token += 1
        token = self._last_query_table_token

        async def work_async() -> None:
            import asyncio

            columns: list[Any] = []
            try:
                runtime = getattr(self.services, "runtime", None)
                use_worker = bool(getattr(runtime, "process_worker", False)) and not bool(
                    getattr(getattr(runtime, "mock", None), "enabled", False)
                )
                client = None
                if use_worker and hasattr(self, "_get_process_worker_client_async"):
                    client = await self._get_process_worker_client_async()  # type: ignore[attr-defined]

                if client is not None and hasattr(client, "list_columns") and self.current_config is not None:
                    outcome = await asyncio.to_thread(
                        client.list_columns,
                        config=self.current_config,
                        database=database,
                        schema=schema,
                        name=name,
                    )
                    if getattr(outcome, "cancelled", False):
                        return
                    error = getattr(outcome, "error", None)
                    if error:
                        raise RuntimeError(error)
                    columns = outcome.columns or []
                else:
                    schema_service = self._get_schema_service()
                    if schema_service:
                        columns = await asyncio.to_thread(
                            schema_service.list_columns,
                            database,
                            schema,
                            name,
                        )
            except Exception:
                columns = []

            self._schedule_timer(
                MIN_TIMER_DELAY_S,
                lambda: self._apply_last_query_table_columns(
                    token,
                    database,
                    schema,
                    name,
                    columns,
                ),
            )

        self.run_worker(work_async(), name=f"prime-last-query-columns-{name}", exclusive=False)

    def _apply_last_query_table_columns(
        self: TreeMixinHost,
        token: int,
        database: str | None,
        schema: str | None,
        name: str,
        columns: list[Any],
    ) -> None:
        if token != self._last_query_table_token:
            return
        table_info = getattr(self, "_last_query_table", None)
        if not table_info:
            return
        if (
            table_info.get("database") != database
            or table_info.get("schema") != schema
            or table_info.get("name") != name
        ):
            return
        table_info["columns"] = columns

    def _schedule_expanded_state_persist(self: TreeMixinHost) -> None:
        timer = getattr(self, "_expanded_state_save_timer", None)
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
        self._expanded_state_save_timer = self._schedule_timer(
            0.2,
            lambda: tree_expansion_state.persist_expanded_state(self),
        )

    def _ensure_database_connection_async(
        self: TreeMixinHost,
        target_db: str,
        on_ready: Any | None = None,
    ) -> None:
        if not self.current_provider or not self.current_config:
            return
        caps = self.current_provider.capabilities
        if caps.supports_cross_database_queries:
            tree_db_switching.set_default_database(self, target_db)
            if callable(on_ready):
                on_ready()
            return
        endpoint = self.current_config.tcp_endpoint
        current_db = endpoint.database if endpoint else ""
        if current_db and current_db.lower() == target_db.lower():
            if callable(on_ready):
                on_ready()
            return
        self._switch_database_async(target_db, on_ready=on_ready)

    def _switch_database_async(
        self: TreeMixinHost,
        db_name: str,
        on_ready: Any | None = None,
    ) -> None:
        if not self._session:
            return
        session = self._session
        session_id = id(session)
        self._db_switch_token += 1
        token = self._db_switch_token

        if hasattr(self, "_clear_query_target_database"):
            self._clear_query_target_database()

        def work() -> None:
            try:
                session.switch_database(db_name)
            except Exception as error:
                self.call_from_thread(self._on_database_switch_error, token, db_name, error)
                return
            self.call_from_thread(self._on_database_switch_success, token, session_id, db_name, on_ready)

        self.run_worker(work, name=f"switch-db-{db_name}", thread=True, exclusive=True)

    def _on_database_switch_success(
        self: TreeMixinHost,
        token: int,
        session_id: int,
        db_name: str,
        on_ready: Any | None,
    ) -> None:
        if token != self._db_switch_token:
            return
        if not self._session or id(self._session) != session_id:
            return
        self.current_config = self._session.config
        self.current_connection = self._session.connection
        self._active_database = db_name
        self.notify(f"Switched to database: {db_name}")
        self._update_status_bar()
        tree_db_switching.update_database_labels(self)
        self._get_object_cache().clear()
        loader = getattr(self, "_load_schema_cache", None)
        if callable(loader):
            request_token = object()
            setattr(self, "_schema_load_request_token", request_token)

            def run_loader() -> None:
                if getattr(self, "_schema_load_request_token", None) is not request_token:
                    return
                loader()

            try:
                from sqlit.domains.shell.app.idle_scheduler import Priority, get_idle_scheduler
            except Exception:
                scheduler = None
            else:
                scheduler = get_idle_scheduler()
            if scheduler:
                scheduler.request_idle_callback(
                    run_loader,
                    priority=Priority.LOW,
                    name="schema-load",
                )
            else:
                self._schedule_timer(MIN_TIMER_DELAY_S, run_loader)
        if callable(on_ready):
            on_ready()

    def _on_database_switch_error(self: TreeMixinHost, token: int, db_name: str, error: Exception) -> None:
        if token != self._db_switch_token:
            return
        self.notify(f"Failed to connect to {db_name}: {error}", severity="error")
