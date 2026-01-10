"""Connection management mixin for SSMSTUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from sqlit.domains.connections.app.connection_flow import ConnectionFlow, ConnectionPrompter
from sqlit.domains.connections.app.session import ConnectionSession
from sqlit.domains.explorer.ui.tree import builder as tree_builder
from sqlit.domains.explorer.ui.tree import db_switching as tree_db_switching
from sqlit.shared.ui.protocols import ConnectionMixinHost
from sqlit.shared.ui.spinner import Spinner

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig
    from sqlit.domains.connections.providers.model import DatabaseProvider


class _ScreenPrompter(ConnectionPrompter):
    def __init__(self, host: ConnectionMixinHost) -> None:
        self._host = host

    def prompt_ssh_password(self, config: ConnectionConfig, on_done: Any) -> None:
        from ..screens import PasswordInputScreen

        self._host.push_screen(
            PasswordInputScreen(config.name, password_type="ssh"),
            on_done,
        )

    def prompt_db_password(self, config: ConnectionConfig, on_done: Any) -> None:
        from ..screens import PasswordInputScreen

        self._host.push_screen(
            PasswordInputScreen(config.name, password_type="database"),
            on_done,
        )


class ConnectionMixin:
    """Mixin providing connection management functionality."""

    current_config: ConnectionConfig | None = None
    current_provider: DatabaseProvider | None = None
    _connecting_config: ConnectionConfig | None = None
    _connect_spinner: Spinner | None = None
    _active_database: str | None = None
    _session: ConnectionSession | None = None
    _query_target_database: str | None = None

    _connection_flow: ConnectionFlow | None = None

    def _emit_debug(self: ConnectionMixinHost, name: str, **data: Any) -> None:
        emit = getattr(self, "emit_debug_event", None)
        if callable(emit):
            emit(name, **data)

    def watch_current_config(self: ConnectionMixinHost, old_config: ConnectionConfig | None, new_config: ConnectionConfig | None) -> None:
        if not getattr(self, "_screen_stack", None):
            return
        self._update_status_bar()
        self._update_section_labels()
        pending_runner = getattr(self, "_maybe_run_pending_telescope_query", None)
        if callable(pending_runner):
            pending_runner()
        if old_config and new_config and self._connection_identity(old_config) == self._connection_identity(new_config):
            try:
                tree_db_switching.update_database_labels(self)
            except Exception:
                pass
            return
        self._refresh_connection_tree()

    def _connection_identity(self, config: ConnectionConfig) -> tuple[Any, ...]:
        if config.file_endpoint:
            return ("file", config.name, config.db_type, config.file_endpoint.path)
        endpoint = config.tcp_endpoint
        host = endpoint.host if endpoint else ""
        port = endpoint.port if endpoint else ""
        return ("tcp", config.name, config.db_type, host, port)

    def _refresh_connection_tree(self: ConnectionMixinHost) -> None:
        screen_stack = getattr(self, "_screen_stack", None)
        if not screen_stack:
            return

        token = object()
        setattr(self, "_connection_tree_refresh_token", token)

        def do_refresh() -> None:
            if getattr(self, "_connection_tree_refresh_token", None) is not token:
                return

            def after_refresh() -> None:
                try:
                    self.call_after_refresh(self._select_connected_node)
                    self.call_after_refresh(lambda: tree_db_switching.update_database_labels(self))
                except Exception:
                    pass

            tree_builder.refresh_tree_chunked(self, on_done=after_refresh)

        try:
            from sqlit.domains.shell.app.idle_scheduler import Priority, get_idle_scheduler
        except Exception:
            scheduler = None
        else:
            scheduler = get_idle_scheduler()
        if scheduler:
            scheduler.request_idle_callback(
                do_refresh,
                priority=Priority.NORMAL,
                name="connection-tree-refresh",
            )
        else:
            self.set_timer(0.001, do_refresh)

    def _get_connection_flow(self: ConnectionMixinHost) -> ConnectionFlow:
        flow = getattr(self, "_connection_flow", None)
        manager = getattr(self, "_connection_manager", None)
        if flow is None:
            flow = ConnectionFlow(
                services=self.services,
                connection_manager=manager,
                prompter=_ScreenPrompter(self),
                emit_debug=getattr(self, "emit_debug_event", None),
            )
            self._connection_flow = flow
        else:
            flow.connection_manager = manager
        return flow

    def _get_connection_config_from_data(self, data: Any) -> ConnectionConfig | None:
        if data is None:
            return None
        getter = getattr(data, "get_connection_config", None)
        if callable(getter):
            from sqlit.domains.connections.domain.config import ConnectionConfig

            value = getter()
            return value if isinstance(value, ConnectionConfig) else None
        return None

    def _get_connection_config_from_node(self, node: Any) -> ConnectionConfig | None:
        data = getattr(node, "data", None)
        return self._get_connection_config_from_data(data)

    def _find_connection_node_by_name(self: ConnectionMixinHost, name: str) -> Any | None:
        if not name:
            return None
        stack = [self.object_tree.root]
        while stack:
            node = stack.pop()
            for child in node.children:
                config = self._get_connection_config_from_node(child)
                if config and config.name == name:
                    return child
                stack.append(child)
        return None

    def _get_connection_folder_path(self: ConnectionMixinHost, node: Any) -> str | None:
        if not node or self._get_node_kind(node) != "connection_folder":
            return None
        parts: list[str] = []
        current = node
        while current and current != self.object_tree.root:
            if self._get_node_kind(current) == "connection_folder":
                data = getattr(current, "data", None)
                name = getattr(data, "name", None)
                if isinstance(name, str) and name:
                    parts.append(name)
            current = current.parent
        if not parts:
            return None
        return "/".join(reversed(parts))

    def connect_to_server(self: ConnectionMixinHost, config: ConnectionConfig) -> None:
        """Connect to a database (async, non-blocking).

        If the connection requires a password that is not stored (empty),
        the user will be prompted to enter the password before connecting.
        """
        self._emit_debug(
            "connection.request",
            connection=config.name,
            db_type=str(config.db_type),
        )
        flow = self._get_connection_flow()
        flow.start(config, self._do_connect)

    def _set_connecting_state(self: ConnectionMixinHost, config: ConnectionConfig | None, refresh: bool = True) -> None:
        """Track which connection is currently being attempted."""
        previous_config = getattr(self, "_connecting_config", None)
        self._connecting_config = config
        if config is None:
            self._stop_connect_spinner()
            if previous_config is not None:
                tree_builder.clear_connecting_indicator(self, previous_config)
            try:
                self._update_status_bar()
            except Exception:
                pass
            return

        self._start_connect_spinner()
        if refresh:
            tree_builder.ensure_connecting_indicator(self, config)
        tree_builder.update_connecting_indicator(self)
        try:
            self._update_status_bar()
        except Exception:
            pass

    def _start_connect_spinner(self: ConnectionMixinHost) -> None:
        """Start the connection spinner animation."""
        if self._connect_spinner is not None:
            self._connect_spinner.stop()
        self._connect_spinner = Spinner(self, on_tick=lambda _: self._on_connect_spinner_tick(), fps=30)
        self._connect_spinner.start()

    def _stop_connect_spinner(self: ConnectionMixinHost) -> None:
        """Stop the connection spinner animation."""
        if self._connect_spinner is not None:
            self._connect_spinner.stop()
            self._connect_spinner = None

    def _on_connect_spinner_tick(self: ConnectionMixinHost) -> None:
        """Update UI on connect spinner tick."""
        if not getattr(self, "_connecting_config", None):
            return
        tree_builder.update_connecting_indicator(self)
        try:
            self._update_status_bar()
        except Exception:
            pass

    def _do_connect(self: ConnectionMixinHost, config: ConnectionConfig) -> None:
        # Disconnect from current server first (if any)
        if self.current_connection is not None:
            self._disconnect_silent()

        self._connection_failed = False
        self._set_connecting_state(config, refresh=True)

        # Track connection attempt to ignore stale callbacks
        if not hasattr(self, "_connection_attempt_id"):
            self._connection_attempt_id = 0
        self._connection_attempt_id += 1
        attempt_id = self._connection_attempt_id
        self._emit_debug(
            "connection.attempt_start",
            connection=config.name,
            db_type=str(config.db_type),
            attempt_id=attempt_id,
        )

        def work() -> ConnectionSession:
            manager = getattr(self, "_connection_manager", None)
            if manager is not None:
                return cast(ConnectionSession, manager.connect(config))
            return cast(ConnectionSession, self.services.session_factory(config))

        def on_success(session: ConnectionSession) -> None:
            # Ignore if a newer connection attempt was started
            if attempt_id != self._connection_attempt_id:
                session.close()
                return

            self._connection_failed = False
            self._session = session
            self.current_provider = session.provider
            self.current_ssh_tunnel = session.tunnel
            is_saved = any(c.name == config.name for c in self.connections)
            self._direct_connection_config = None if is_saved else config
            self._active_database = None
            self.current_connection = session.connection
            self.current_config = config
            self._set_connecting_state(None, refresh=False)
            reconnected = False
            if not reconnected:
                def load_schema_cache() -> None:
                    if attempt_id != self._connection_attempt_id:
                        return
                    if self.current_connection is None or self.current_config is None:
                        return
                    self._load_schema_cache()

                if getattr(self, "_pending_telescope_query", None) or getattr(self, "_defer_schema_load", False):
                    setattr(self, "_defer_schema_load", True)
                else:
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
                        scheduler.cancel_all(name="schema-cache-load")
                        scheduler.request_idle_callback(
                            load_schema_cache,
                            priority=Priority.NORMAL,
                            name="schema-cache-load",
                        )
                    else:
                        self.set_timer(0.25, load_schema_cache)
            connect_hook = getattr(self, "_on_connect", None)
            if callable(connect_hook):
                connect_hook()
            if self.current_provider:
                for message in self.current_provider.post_connect_warnings(config):
                    self.notify(message, severity="warning")
            self._emit_debug(
                "connection.attempt_success",
                connection=config.name,
                attempt_id=attempt_id,
            )

        def on_error(error: Exception) -> None:
            # Ignore if a newer connection attempt was started
            if attempt_id != self._connection_attempt_id:
                return

            self._set_connecting_state(None, refresh=True)
            from sqlit.shared.ui.screens.error import ErrorScreen

            from ..connection_error_handlers import handle_connection_error

            self._connection_failed = True
            self._update_status_bar()

            connect_failed = getattr(self, "_on_connect_failed", None)
            if callable(connect_failed):
                connect_failed(config)

            self._emit_debug(
                "connection.attempt_error",
                connection=config.name,
                attempt_id=attempt_id,
                error=str(error),
            )

            if handle_connection_error(self, error, config):
                return

            self.push_screen(ErrorScreen("Connection Failed", str(error)))

        def do_work() -> None:
            try:
                session = work()
                self.call_from_thread(on_success, session)
            except Exception as e:
                self.call_from_thread(on_error, e)

        # Use fixed name so exclusive=True cancels any previous connection attempt
        self.run_worker(do_work, name="connect", thread=True, exclusive=True)

    def _disconnect_silent(self: ConnectionMixinHost) -> None:
        """Disconnect without user notification.

        Closes the session, clears connection state, and refreshes the tree.
        Called 'silent' because it doesn't notify the user, but it does update the UI.
        """
        session = getattr(self, "_session", None)
        self._session = None
        if session is not None:
            def close_session() -> None:
                try:
                    session.close()
                except Exception:
                    pass
            try:
                self.run_worker(close_session, name="close-session", thread=True, exclusive=False)
            except Exception:
                try:
                    session.close()
                except Exception:
                    pass

        self.current_connection = None
        self.current_config = None
        self.current_provider = None
        self.current_ssh_tunnel = None
        self._direct_connection_config = None
        self._active_database = None
        self._clear_query_target_database()
        # Notify all mixins of disconnect via lifecycle hook
        self._on_disconnect()

    def _select_connected_node(self: ConnectionMixinHost) -> None:
        """Move cursor to the connected node without toggling expansion."""
        if not self.current_config:
            return
        cursor = self.object_tree.cursor_node
        if cursor is not None:
            cursor_config = self._get_connection_config_from_node(cursor)
            if not cursor_config or cursor_config.name != self.current_config.name:
                return
        node = self._find_connection_node_by_name(self.current_config.name)
        if node is not None:
            self.object_tree.move_cursor(node)

    def action_disconnect(self: ConnectionMixinHost) -> None:
        """Disconnect from current database."""
        if self.current_connection is not None:
            self._disconnect_silent()
            self.status_bar.update("Disconnected")
            self.notify("Disconnected")

    def _get_effective_database(self: ConnectionMixinHost) -> str | None:
        """Return the active database for the current connection context."""
        if not self.current_provider or not self.current_config:
            return None
        if self.current_provider.capabilities.supports_cross_database_queries:
            endpoint = self.current_config.tcp_endpoint
            db_name = getattr(self, "_active_database", None) or (endpoint.database if endpoint else "")
            return db_name or None
        endpoint = self.current_config.tcp_endpoint
        db_name = endpoint.database if endpoint else ""
        return db_name or None

    def _get_metadata_db_arg(self: ConnectionMixinHost, database: str | None) -> str | None:
        """Return database arg for metadata calls when cross-db queries are supported."""
        if not database or not self.current_provider:
            return None
        if self.current_provider.capabilities.supports_cross_database_queries:
            return database
        return None

    def _clear_query_target_database(self: ConnectionMixinHost) -> None:
        """Clear any pending per-query database override."""
        if hasattr(self, "_query_target_database"):
            self._query_target_database = None

    def action_new_connection(self: ConnectionMixinHost) -> None:
        from ..screens import ConnectionScreen

        self._set_connection_screen_footer()
        self.push_screen(ConnectionScreen(), self._wrap_connection_result)

    def action_edit_connection(self: ConnectionMixinHost) -> None:
        from ..screens import ConnectionScreen

        node = self.object_tree.cursor_node

        if not node:
            return

        config = self._get_connection_config_from_node(node)
        if not config:
            return

        self._set_connection_screen_footer()
        self.push_screen(ConnectionScreen(config, editing=True), self._wrap_connection_result)

    def _set_connection_screen_footer(self: ConnectionMixinHost) -> None:
        from sqlit.shared.ui.widgets import ContextFooter

        try:
            footer = self.query_one(ContextFooter)
        except Exception:
            return
        footer.set_bindings([], [])

    def _wrap_connection_result(self: ConnectionMixinHost, result: tuple | None) -> None:
        self._update_footer_bindings()
        self.handle_connection_result(result)

    def handle_connection_result(self: ConnectionMixinHost, result: tuple | None) -> None:
        from sqlit.domains.connections.app.credentials import (
            ALLOW_PLAINTEXT_CREDENTIALS_SETTING,
            build_credentials_service,
            is_keyring_usable,
            reset_credentials_service,
        )
        from sqlit.shared.ui.screens.confirm import ConfirmScreen

        if not result:
            return

        action, config = result[0], result[1]
        original_name = result[2] if len(result) > 2 else None

        if action == "save":
            def do_save(with_config: ConnectionConfig, orig_name: str | None = None) -> None:
                from sqlit.domains.connections.app.credentials import CredentialsPersistError
                from sqlit.shared.ui.screens.error import ErrorScreen

                credentials_error: CredentialsPersistError | None = None
                # When editing, remove by original name to properly update renamed connections
                if orig_name:
                    self.connections = [c for c in self.connections if c.name != orig_name]
                # Also remove by new name to handle overwrites/duplicates
                self.connections = [c for c in self.connections if c.name != with_config.name]
                self.connections.append(with_config)
                if not self.services.connection_store.is_persistent:
                    self.notify("Connections are not persisted in this session")
                try:
                    persist_connections = self.connections
                    if self.services.connection_store.is_persistent:
                        try:
                            persist_connections = self.services.connection_store.load_all()
                        except Exception:
                            persist_connections = self.connections
                        else:
                            if orig_name:
                                persist_connections = [
                                    c for c in persist_connections if c.name != orig_name
                                ]
                            persist_connections = [
                                c for c in persist_connections if c.name != with_config.name
                            ]
                            persist_connections.append(with_config)
                    self.services.connection_store.save_all(persist_connections)
                except CredentialsPersistError as exc:
                    credentials_error = exc
                self._refresh_connection_tree()
                self.notify(f"Connection '{with_config.name}' saved")
                if credentials_error:
                    self.push_screen(ErrorScreen("Keyring Error", str(credentials_error)))

            endpoint = config.tcp_endpoint
            needs_password_persist = bool(
                (endpoint and endpoint.password) or (config.tunnel and config.tunnel.password)
            )
            if needs_password_persist and not is_keyring_usable():
                settings = self.services.settings_store.load_all()
                allow_plaintext = settings.get(ALLOW_PLAINTEXT_CREDENTIALS_SETTING)

                if allow_plaintext is True:
                    reset_credentials_service()
                    self.services.credentials_service = build_credentials_service(self.services.settings_store)
                    self.services.connection_store.set_credentials_service(self.services.credentials_service)
                    do_save(config, original_name)
                    return

                if allow_plaintext is False:
                    if endpoint:
                        endpoint.password = ""
                    if config.tunnel:
                        config.tunnel.password = ""
                    do_save(config, original_name)
                    self.notify("Keyring unavailable: passwords will be prompted when needed", severity="warning")
                    return

                def on_confirm(confirmed: bool | None) -> None:
                    settings2 = self.services.settings_store.load_all()
                    if confirmed is True:
                        settings2[ALLOW_PLAINTEXT_CREDENTIALS_SETTING] = True
                        self.services.settings_store.save_all(settings2)
                        reset_credentials_service()
                        self.services.credentials_service = build_credentials_service(self.services.settings_store)
                        self.services.connection_store.set_credentials_service(self.services.credentials_service)
                        do_save(config, original_name)
                        self.notify("Saved passwords as plaintext in ~/.sqlit/ (0600)", severity="warning")
                        return

                    settings2[ALLOW_PLAINTEXT_CREDENTIALS_SETTING] = False
                    self.services.settings_store.save_all(settings2)
                    if endpoint:
                        endpoint.password = ""
                    if config.tunnel:
                        config.tunnel.password = ""
                    do_save(config, original_name)
                    self.notify("Passwords were not saved (keyring unavailable)", severity="warning")

                self.push_screen(
                    ConfirmScreen(
                        "Keyring isn't available",
                        "Save passwords as plaintext in ~/.sqlit/ (protected directory)?",
                        yes_label="Yes",
                        no_label="No",
                    ),
                    on_confirm,
                )
                return

            do_save(config, original_name)

    def action_duplicate_connection(self: ConnectionMixinHost) -> None:
        from dataclasses import replace

        from ..screens import ConnectionScreen

        node = self.object_tree.cursor_node

        if not node:
            return

        config = self._get_connection_config_from_node(node)
        if not config:
            return

        existing_names = {c.name for c in self.connections}
        base_name = config.name
        new_name = f"{base_name} (copy)"
        counter = 2
        while new_name in existing_names:
            new_name = f"{base_name} (copy {counter})"
            counter += 1

        duplicated = replace(config, name=new_name)

        self._set_connection_screen_footer()
        self.push_screen(ConnectionScreen(duplicated, editing=False), self._wrap_connection_result)

    def action_toggle_connection_favorite(self: ConnectionMixinHost) -> None:
        from sqlit.domains.connections.app.credentials import CredentialsPersistError
        from sqlit.shared.ui.screens.error import ErrorScreen

        node = self.object_tree.cursor_node
        if not node:
            return

        config = self._get_connection_config_from_node(node)
        if not config:
            return

        if not any(c.name == config.name for c in self.connections):
            self.notify("Only saved connections can be starred", severity="warning")
            return

        previous = config.favorite
        config.favorite = not previous
        credentials_error: CredentialsPersistError | None = None

        try:
            self.services.connection_store.save_all(self.connections)
        except CredentialsPersistError as exc:
            credentials_error = exc
        except Exception as exc:
            config.favorite = previous
            self.notify(f"Failed to update favorite: {exc}", severity="error")
            return

        if not self.services.connection_store.is_persistent:
            self.notify("Connections are not persisted in this session", severity="warning")

        self._refresh_connection_tree()
        if config.favorite:
            self.notify("Connection starred")
        else:
            self.notify("Connection unstarred")
        if credentials_error:
            self.push_screen(ErrorScreen("Keyring Error", str(credentials_error)))

    def action_move_connection_to_folder(self: ConnectionMixinHost) -> None:
        from sqlit.domains.connections.app.credentials import CredentialsPersistError
        from sqlit.domains.connections.domain.config import normalize_folder_path
        from sqlit.domains.connections.ui.screens import FolderInputScreen
        from sqlit.shared.ui.screens.error import ErrorScreen

        node = self.object_tree.cursor_node
        if not node:
            return

        config = self._get_connection_config_from_node(node)
        if not config:
            return

        if not any(c.name == config.name for c in self.connections):
            self.notify("Only saved connections can be moved", severity="warning")
            return

        current_path = getattr(config, "folder_path", "")

        def on_result(value: str | None) -> None:
            if value is None:
                return
            new_path = normalize_folder_path(value)
            if new_path == current_path:
                return
            config.folder_path = new_path
            credentials_error: CredentialsPersistError | None = None

            try:
                self.services.connection_store.save_all(self.connections)
            except CredentialsPersistError as exc:
                credentials_error = exc
            except Exception as exc:
                config.folder_path = current_path
                self.notify(f"Failed to move connection: {exc}", severity="error")
                return

            if not self.services.connection_store.is_persistent:
                self.notify("Connections are not persisted in this session", severity="warning")

            self._refresh_connection_tree()
            if new_path:
                self.notify(f"Moved to folder '{new_path}'")
            else:
                self.notify("Moved to root")
            if credentials_error:
                self.push_screen(ErrorScreen("Keyring Error", str(credentials_error)))

        self.push_screen(
            FolderInputScreen(config.name, current_value=current_path),
            on_result,
        )

    def action_rename_connection_folder(self: ConnectionMixinHost) -> None:
        from sqlit.domains.connections.app.credentials import CredentialsPersistError
        from sqlit.domains.connections.domain.config import normalize_folder_path
        from sqlit.domains.connections.ui.screens import FolderInputScreen
        from sqlit.shared.ui.screens.error import ErrorScreen

        node = self.object_tree.cursor_node
        folder_path = self._get_connection_folder_path(node)
        if not folder_path:
            return

        parent_path = "/".join(folder_path.split("/")[:-1])
        current_name = folder_path.split("/")[-1]

        def on_result(value: str | None) -> None:
            if value is None:
                return
            new_segment = normalize_folder_path(value)
            if not new_segment:
                self.notify("Folder name cannot be empty", severity="warning")
                return
            new_path = f"{parent_path}/{new_segment}" if parent_path else new_segment
            if new_path == folder_path:
                return

            updated = False
            for conn in self.connections:
                path = getattr(conn, "folder_path", "") or ""
                if path == folder_path or path.startswith(f"{folder_path}/"):
                    remainder = "" if path == folder_path else path[len(folder_path) + 1 :]
                    conn.folder_path = f"{new_path}/{remainder}" if remainder else new_path
                    updated = True

            if not updated:
                return

            credentials_error: CredentialsPersistError | None = None
            try:
                self.services.connection_store.save_all(self.connections)
            except CredentialsPersistError as exc:
                credentials_error = exc
            except Exception as exc:
                self.notify(f"Failed to rename folder: {exc}", severity="error")
                return

            if not self.services.connection_store.is_persistent:
                self.notify("Connections are not persisted in this session", severity="warning")

            self._refresh_connection_tree()
            self.notify(f"Renamed folder to '{new_path}'")
            if credentials_error:
                self.push_screen(ErrorScreen("Keyring Error", str(credentials_error)))

        self.push_screen(
            FolderInputScreen(
                current_name,
                current_value=current_name,
                title="Rename Folder",
                description=f"Rename folder '{folder_path}' (use / for nesting):",
            ),
            on_result,
        )

    def action_delete_connection_folder(self: ConnectionMixinHost) -> None:
        from sqlit.domains.connections.app.credentials import CredentialsPersistError
        from sqlit.shared.ui.screens.confirm import ConfirmScreen
        from sqlit.shared.ui.screens.error import ErrorScreen

        node = self.object_tree.cursor_node
        folder_path = self._get_connection_folder_path(node)
        if not folder_path:
            return

        parent_path = "/".join(folder_path.split("/")[:-1])

        def do_delete(confirmed: bool | None) -> None:
            if not confirmed:
                return

            updated = False
            for conn in self.connections:
                path = getattr(conn, "folder_path", "") or ""
                if path == folder_path or path.startswith(f"{folder_path}/"):
                    remainder = "" if path == folder_path else path[len(folder_path) + 1 :]
                    if parent_path:
                        new_path = f"{parent_path}/{remainder}" if remainder else parent_path
                    else:
                        new_path = remainder
                    conn.folder_path = new_path
                    updated = True

            if not updated:
                return

            credentials_error: CredentialsPersistError | None = None
            try:
                self.services.connection_store.save_all(self.connections)
            except CredentialsPersistError as exc:
                credentials_error = exc
            except Exception as exc:
                self.notify(f"Failed to delete folder: {exc}", severity="error")
                return

            if not self.services.connection_store.is_persistent:
                self.notify("Connections are not persisted in this session", severity="warning")

            self._refresh_connection_tree()
            self.notify(f"Deleted folder '{folder_path}'")
            if credentials_error:
                self.push_screen(ErrorScreen("Keyring Error", str(credentials_error)))

        self.push_screen(
            ConfirmScreen(
                f"Delete folder '{folder_path}'?",
                "Connections will move to the parent folder.",
            ),
            do_delete,
        )

    def action_delete_connection(self: ConnectionMixinHost) -> None:
        from sqlit.shared.ui.screens.confirm import ConfirmScreen

        node = self.object_tree.cursor_node

        if not node:
            return

        config = self._get_connection_config_from_node(node)
        if not config:
            return
        is_connected = self.current_config and self.current_config.name == config.name

        def do_delete(confirmed: bool | None) -> None:
            if not confirmed:
                return
            if is_connected:
                self._disconnect_silent()
            self._do_delete_connection(config)

        self.push_screen(
            ConfirmScreen(f"Delete '{config.name}'?"),
            do_delete,
        )

    def _do_delete_connection(self: ConnectionMixinHost, config: ConnectionConfig) -> None:
        from sqlit.domains.connections.app.credentials import CredentialsPersistError
        from sqlit.shared.ui.screens.error import ErrorScreen

        credentials_error: CredentialsPersistError | None = None
        self.connections = [c for c in self.connections if c.name != config.name]
        if not self.services.connection_store.is_persistent:
            self.notify("Connections are not persisted in this session")
        try:
            self.services.connection_store.save_all(self.connections)
        except CredentialsPersistError as exc:
            credentials_error = exc
        self._refresh_connection_tree()
        self.notify(f"Connection '{config.name}' deleted")
        if credentials_error:
            self.push_screen(ErrorScreen("Keyring Error", str(credentials_error)))

    def action_connect_selected(self: ConnectionMixinHost) -> None:
        node = self.object_tree.cursor_node

        if not node:
            return

        config = self._get_connection_config_from_node(node)
        if not config:
            return
        if self.current_config and self.current_config.name == config.name:
            return
        # Don't disconnect here - we'll disconnect only after successful connection
        self.connect_to_server(config)

    def action_show_connection_picker(self: ConnectionMixinHost) -> None:
        from ..screens import ConnectionPickerScreen

        self._emit_debug("connection_picker.open_request")
        self.push_screen(
            ConnectionPickerScreen(self.connections),
            self._handle_connection_picker_result,
        )

    def _handle_connection_picker_result(self: ConnectionMixinHost, result: Any) -> None:
        if result is None:
            self._emit_debug("connection_picker.result", result="none")
            return

        # Handle special "new connection" action
        if result == "__new_connection__":
            self._emit_debug("connection_picker.result", result="new_connection")
            self.action_new_connection()
            return

        from sqlit.domains.connections.domain.config import ConnectionConfig

        if isinstance(result, ConnectionConfig):
            config = result
            self._emit_debug(
                "connection_picker.result",
                result="config",
                connection=config.name,
                db_type=str(config.db_type),
            )
            matching_config = next((c for c in self.connections if c.name == config.name), None)
            if matching_config:
                config = matching_config
            node = self._find_connection_node_by_name(config.name)
            if node is not None:
                self._emit_debug(
                    "connection_picker.select_node",
                    connection=config.name,
                )
                self.object_tree.move_cursor(node)
            if self.current_config and self.current_config.name == config.name:
                self._emit_debug("connection_picker.already_connected", connection=config.name)
                self.notify(f"Already connected to {config.name}")
                return
            self._emit_debug("connection_picker.connect", connection=config.name)
            self.connect_to_server(config)
            return

        selected_config = next((c for c in self.connections if c.name == result), None)
        if selected_config:
            self._emit_debug("connection_picker.result", result="name", connection=selected_config.name)
            node = self._find_connection_node_by_name(result)
            if node is not None:
                self._emit_debug("connection_picker.select_node", connection=selected_config.name)
                self.object_tree.move_cursor(node)

            if self.current_config and self.current_config.name == selected_config.name:
                self._emit_debug("connection_picker.already_connected", connection=selected_config.name)
                self.notify(f"Already connected to {selected_config.name}")
                return
            self._emit_debug("connection_picker.connect", connection=selected_config.name)
            # Don't disconnect here - we'll disconnect only after successful connection
            self.connect_to_server(selected_config)
