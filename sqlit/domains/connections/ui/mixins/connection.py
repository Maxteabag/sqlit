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

        def after_refresh() -> None:
            try:
                self.call_after_refresh(self._select_connected_node)
                self.call_after_refresh(lambda: tree_db_switching.update_database_labels(self))
            except Exception:
                pass

        tree_builder.refresh_tree_chunked(self, on_done=after_refresh)

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
        for node in self.object_tree.root.children:
            config = self._get_connection_config_from_node(node)
            if config and config.name == self.current_config.name:
                self.object_tree.move_cursor(node)
                break

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
                    self.services.connection_store.save_all(self.connections)
                except CredentialsPersistError as exc:
                    credentials_error = exc
                tree_builder.refresh_tree(self)
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
        tree_builder.refresh_tree(self)
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
            for node in self.object_tree.root.children:
                node_config = self._get_connection_config_from_node(node)
                if node_config and node_config.name == config.name:
                    self._emit_debug(
                        "connection_picker.select_node",
                        connection=config.name,
                    )
                    self.object_tree.move_cursor(node)
                    break
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
            for node in self.object_tree.root.children:
                node_config = self._get_connection_config_from_node(node)
                if node_config and node_config.name == result:
                    self._emit_debug("connection_picker.select_node", connection=selected_config.name)
                    self.object_tree.move_cursor(node)
                    break

            if self.current_config and self.current_config.name == selected_config.name:
                self._emit_debug("connection_picker.already_connected", connection=selected_config.name)
                self.notify(f"Already connected to {selected_config.name}")
                return
            self._emit_debug("connection_picker.connect", connection=selected_config.name)
            # Don't disconnect here - we'll disconnect only after successful connection
            self.connect_to_server(selected_config)
