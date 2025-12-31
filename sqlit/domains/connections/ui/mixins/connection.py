"""Connection management mixin for SSMSTUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from sqlit.domains.connections.domain.passwords import (
    needs_db_password as _needs_db_password,
    needs_ssh_password as _needs_ssh_password,
)
from sqlit.shared.ui.protocols import ConnectionMixinHost
from sqlit.shared.ui.spinner import Spinner

if TYPE_CHECKING:
    from sqlit.domains.connections.app.session import ConnectionSession
    from sqlit.domains.connections.domain.config import ConnectionConfig
    from sqlit.domains.connections.providers.model import DatabaseProvider


class ConnectionMixin:
    """Mixin providing connection management functionality."""

    current_config: ConnectionConfig | None = None
    current_provider: DatabaseProvider | None = None
    _connecting_config: ConnectionConfig | None = None
    _connect_spinner: Spinner | None = None
    _active_database: str | None = None
    _session: ConnectionSession | None = None
    _query_target_database: str | None = None

    def _populate_credentials_if_missing(self: ConnectionMixinHost, config: ConnectionConfig) -> None:
        """Populate missing credentials from the credentials service."""
        endpoint = config.tcp_endpoint
        if endpoint and endpoint.password is not None and (not config.tunnel or config.tunnel.password is not None):
            return
        service = self.services.credentials_service
        if endpoint and endpoint.password is None:
            password = service.get_password(config.name)
            if password is not None:
                endpoint.password = password
        if config.tunnel and config.tunnel.password is None:
            ssh_password = service.get_ssh_password(config.name)
            if ssh_password is not None:
                config.tunnel.password = ssh_password

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
        from dataclasses import replace

        from ..screens import PasswordInputScreen

        self._populate_credentials_if_missing(config)

        if _needs_ssh_password(config):

            def on_ssh_password(password: str | None) -> None:
                if password is None:
                    return
                temp_config = config.with_tunnel(password=password)
                self._connect_with_db_password_check(temp_config)

            self.push_screen(
                PasswordInputScreen(config.name, password_type="ssh"),
                on_ssh_password,
            )
            return

        self._connect_with_db_password_check(config)

    def _connect_with_db_password_check(self: ConnectionMixinHost, config: ConnectionConfig) -> None:
        """Check for database password and prompt if needed, then connect."""
        from dataclasses import replace

        from ..screens import PasswordInputScreen

        if _needs_db_password(config):

            def on_db_password(password: str | None) -> None:
                if password is None:
                    return
                temp_config = config.with_endpoint(password=password)
                self._do_connect(temp_config)

            self.push_screen(
                PasswordInputScreen(config.name, password_type="database"),
                on_db_password,
            )
            return

        self._do_connect(config)

    def _set_connecting_state(self: ConnectionMixinHost, config: ConnectionConfig | None, refresh: bool = True) -> None:
        """Track which connection is currently being attempted."""
        self._connecting_config = config
        if config is None:
            self._stop_connect_spinner()
            if refresh:
                self.refresh_tree()
            try:
                self._update_status_bar()
            except Exception:
                pass
            return

        self._start_connect_spinner()
        if refresh:
            self.refresh_tree()
        self._update_connecting_indicator()
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
        self._update_connecting_indicator()
        try:
            self._update_status_bar()
        except Exception:
            pass

    def _do_connect(self: ConnectionMixinHost, config: ConnectionConfig) -> None:
        # Disconnect from current server first (if any)
        if self.current_connection:
            self._disconnect_silent()

        self._connection_failed = False
        self._set_connecting_state(config, refresh=True)

        # Track connection attempt to ignore stale callbacks
        if not hasattr(self, "_connection_attempt_id"):
            self._connection_attempt_id = 0
        self._connection_attempt_id += 1
        attempt_id = self._connection_attempt_id

        def work() -> ConnectionSession:
            return cast(ConnectionSession, self.services.session_factory(config))

        def on_success(session: ConnectionSession) -> None:
            # Ignore if a newer connection attempt was started
            if attempt_id != self._connection_attempt_id:
                session.close()
                return

            self._set_connecting_state(None, refresh=False)
            self._connection_failed = False
            self._session = session
            self.current_connection = session.connection
            self.current_config = config
            self.current_provider = session.provider
            self.current_ssh_tunnel = session.tunnel
            is_saved = any(c.name == config.name for c in self.connections)
            self._direct_connection_config = None if is_saved else config
            self._active_database = None
            reconnected = False

            self.refresh_tree()
            self.call_after_refresh(self._select_connected_node)
            if not reconnected:
                self._load_schema_cache()
            self._update_status_bar()
            self._update_section_labels()
            # Update database labels to show star on active database
            if hasattr(self, "_update_database_labels"):
                self.call_after_refresh(self._update_database_labels)
            if self.current_provider:
                for message in self.current_provider.post_connect_warnings(config):
                    self.notify(message, severity="warning")

        def on_error(error: Exception) -> None:
            # Ignore if a newer connection attempt was started
            if attempt_id != self._connection_attempt_id:
                return

            self._set_connecting_state(None, refresh=True)
            from ..connection_error_handlers import handle_connection_error
            from sqlit.shared.ui.screens.error import ErrorScreen

            self._connection_failed = True
            self._update_status_bar()

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
        if hasattr(self, "_session") and self._session:
            self._session.close()
            self._session = None

        self.current_connection = None
        self.current_config = None
        self.current_provider = None
        self.current_ssh_tunnel = None
        self._direct_connection_config = None
        self._active_database = None
        self._clear_query_target_database()
        self.refresh_tree()
        self._update_section_labels()

    def _select_connected_node(self: ConnectionMixinHost) -> None:
        """Move cursor to the connected node without toggling expansion."""
        if not self.current_config:
            return
        for node in self.object_tree.root.children:
            config = self._get_connection_config_from_node(node)
            if config and config.name == self.current_config.name:
                self.object_tree.move_cursor(node)
                break

    def action_disconnect(self: ConnectionMixinHost) -> None:
        """Disconnect from current database."""
        if self.current_connection:
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
            is_keyring_usable,
            reset_credentials_service,
            build_credentials_service,
        )
        from sqlit.shared.ui.screens.confirm import ConfirmScreen

        if not result:
            return

        action, config = result[0], result[1]
        original_name = result[2] if len(result) > 2 else None

        if action == "save":
            def do_save(with_config: ConnectionConfig, orig_name: str | None = None) -> None:
                # When editing, remove by original name to properly update renamed connections
                if orig_name:
                    self.connections = [c for c in self.connections if c.name != orig_name]
                # Also remove by new name to handle overwrites/duplicates
                self.connections = [c for c in self.connections if c.name != with_config.name]
                self.connections.append(with_config)
                if not self.services.connection_store.is_persistent:
                    self.notify("Connections are not persisted in this session")
                self.services.connection_store.save_all(self.connections)
                self.refresh_tree()
                self.notify(f"Connection '{with_config.name}' saved")

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
        self.connections = [c for c in self.connections if c.name != config.name]
        if not self.services.connection_store.is_persistent:
            self.notify("Connections are not persisted in this session")
        self.services.connection_store.save_all(self.connections)
        self.refresh_tree()
        self.notify(f"Connection '{config.name}' deleted")

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

        self.push_screen(
            ConnectionPickerScreen(self.connections),
            self._handle_connection_picker_result,
        )

    def _get_connection_result_registry(self) -> Any:
        registry = getattr(self, "_connection_result_registry", None)
        if registry is None:
            from sqlit.domains.connections.ui.handlers.connection_picker import (
                get_default_connection_result_registry,
            )

            registry = get_default_connection_result_registry()
            self._connection_result_registry = registry
        return registry

    def _handle_connection_picker_result(self: ConnectionMixinHost, result: Any) -> None:
        if result is None:
            return

        # Handle special "new connection" action
        if result == "__new_connection__":
            self.action_new_connection()
            return

        result_kind = getattr(result, "get_result_kind", None)
        if callable(result_kind):
            kind = result_kind()
            registry = self._get_connection_result_registry()
            if registry.handle(self, kind, result):
                return

        # Handle saved connection selection
        config = next((c for c in self.connections if c.name == result), None)
        if config:
            for node in self.object_tree.root.children:
                node_config = self._get_connection_config_from_node(node)
                if node_config and node_config.name == result:
                    self.object_tree.select_node(node)
                    break

            if self.current_config and self.current_config.name == config.name:
                self.notify(f"Already connected to {config.name}")
                return
            # Don't disconnect here - we'll disconnect only after successful connection
            self.connect_to_server(config)
