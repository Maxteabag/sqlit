"""Connection management mixin for SSMSTUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..protocols import AppProtocol
from .query import SPINNER_FRAMES

if TYPE_CHECKING:
    from ...config import ConnectionConfig
    from ...db import DatabaseAdapter
    from ...services.docker_detector import DetectedContainer
    from ..screens.connection_picker import DockerConnectionResult


def _needs_db_password(config: ConnectionConfig) -> bool:
    """Check if the connection needs a database password prompt.

    Returns True if password is None (not set) and the database type uses passwords.
    An empty string password ("") is considered explicitly set and does not need a prompt.
    """
    from ...db.providers import is_file_based

    # File-based databases (SQLite, DuckDB) don't need passwords
    if is_file_based(config.db_type):
        return False

    # Only prompt if password is None (not set), not for empty string (explicitly empty)
    return config.password is None


def _needs_ssh_password(config: ConnectionConfig) -> bool:
    """Check if the connection needs an SSH password prompt.

    Returns True if SSH is enabled with password auth and password is None (not set).
    An empty string password ("") is considered explicitly set and does not need a prompt.
    """
    if not config.ssh_enabled:
        return False

    if config.ssh_auth_type != "password":
        return False

    # Only prompt if password is None (not set), not for empty string (explicitly empty)
    return config.ssh_password is None


class ConnectionMixin:
    """Mixin providing connection management functionality."""

    current_config: ConnectionConfig | None = None
    current_adapter: DatabaseAdapter | None = None
    _connecting_config: ConnectionConfig | None = None
    _connect_spinner_timer = None
    _connect_spinner_index = 0

    def _populate_credentials_if_missing(self: AppProtocol, config: ConnectionConfig) -> None:
        """Populate missing credentials from the credentials service."""
        if config.password is not None and config.ssh_password is not None:
            return
        from ...services.credentials import get_credentials_service

        service = get_credentials_service()
        if config.password is None:
            password = service.get_password(config.name)
            if password is not None:
                config.password = password
        if config.ssh_password is None:
            ssh_password = service.get_ssh_password(config.name)
            if ssh_password is not None:
                config.ssh_password = ssh_password

    def _get_connection_config_from_data(self, data: Any) -> ConnectionConfig | None:
        if data is None:
            return None
        getter = getattr(data, "get_connection_config", None)
        if callable(getter):
            return getter()
        return None

    def _get_connection_config_from_node(self, node: Any) -> ConnectionConfig | None:
        data = getattr(node, "data", None)
        return self._get_connection_config_from_data(data)

    def connect_to_server(self: AppProtocol, config: ConnectionConfig) -> None:
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
                temp_config = replace(config, ssh_password=password)
                self._connect_with_db_password_check(temp_config)

            self.push_screen(
                PasswordInputScreen(config.name, password_type="ssh"),
                on_ssh_password,
            )
            return

        self._connect_with_db_password_check(config)

    def _connect_with_db_password_check(self: AppProtocol, config: ConnectionConfig) -> None:
        """Check for database password and prompt if needed, then connect."""
        from dataclasses import replace

        from ..screens import PasswordInputScreen

        if _needs_db_password(config):

            def on_db_password(password: str | None) -> None:
                if password is None:
                    return
                temp_config = replace(config, password=password)
                self._do_connect(temp_config)

            self.push_screen(
                PasswordInputScreen(config.name, password_type="database"),
                on_db_password,
            )
            return

        self._do_connect(config)

    def _set_connecting_state(self: AppProtocol, config: ConnectionConfig | None, refresh: bool = True) -> None:
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

    def _start_connect_spinner(self: AppProtocol) -> None:
        """Start the connection spinner animation."""
        self._connect_spinner_index = 0
        if hasattr(self, "_connect_spinner_timer") and self._connect_spinner_timer is not None:
            self._connect_spinner_timer.stop()
        self._connect_spinner_timer = self.set_interval(1 / 30, self._animate_connect_spinner)

    def _stop_connect_spinner(self: AppProtocol) -> None:
        """Stop the connection spinner animation."""
        if hasattr(self, "_connect_spinner_timer") and self._connect_spinner_timer is not None:
            self._connect_spinner_timer.stop()
            self._connect_spinner_timer = None

    def _animate_connect_spinner(self: AppProtocol) -> None:
        """Update connecting spinner animation frame."""
        if not getattr(self, "_connecting_config", None):
            return
        self._connect_spinner_index = (self._connect_spinner_index + 1) % len(SPINNER_FRAMES)
        self._update_connecting_indicator()
        try:
            self._update_status_bar()
        except Exception:
            pass

    def _do_connect(self: AppProtocol, config: ConnectionConfig) -> None:
        from ...services import ConnectionSession

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

        create_session = self._session_factory or ConnectionSession.create

        def work() -> ConnectionSession:
            return create_session(config)

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
            self.current_adapter = session.adapter
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
            if self.current_adapter:
                warnings = self.current_adapter.get_post_connect_warnings(config)
                for message in warnings:
                    self.notify(message, severity="warning")

        def on_error(error: Exception) -> None:
            # Ignore if a newer connection attempt was started
            if attempt_id != self._connection_attempt_id:
                return

            self._set_connecting_state(None, refresh=True)
            from ..connection_error_handlers import handle_connection_error
            from ..screens import ErrorScreen

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

    def _disconnect_silent(self: AppProtocol) -> None:
        """Disconnect without user notification.

        Closes the session, clears connection state, and refreshes the tree.
        Called 'silent' because it doesn't notify the user, but it does update the UI.
        """
        if hasattr(self, "_session") and self._session:
            self._session.close()
            self._session = None

        self.current_connection = None
        self.current_config = None
        self.current_adapter = None
        self.current_ssh_tunnel = None
        self._direct_connection_config = None
        self._active_database = None
        self._clear_query_target_database()
        self.refresh_tree()
        self._update_section_labels()

    def _select_connected_node(self: AppProtocol) -> None:
        """Move cursor to the connected node without toggling expansion."""
        if not self.current_config:
            return
        for node in self.object_tree.root.children:
            config = self._get_connection_config_from_node(node)
            if config and config.name == self.current_config.name:
                self.object_tree.move_cursor(node)
                break

    def action_disconnect(self: AppProtocol) -> None:
        """Disconnect from current database."""
        if self.current_connection:
            self._disconnect_silent()
            self.status_bar.update("Disconnected")
            self.notify("Disconnected")

    def _get_effective_database(self: AppProtocol) -> str | None:
        """Return the active database for the current connection context."""
        if not self.current_adapter or not self.current_config:
            return None
        if self.current_adapter.supports_cross_database_queries:
            db_name = getattr(self, "_active_database", None) or self.current_config.database
            return db_name or None
        db_name = self.current_config.database
        return db_name or None

    def _get_metadata_db_arg(self: AppProtocol, database: str | None) -> str | None:
        """Return database arg for metadata calls when cross-db queries are supported."""
        if not database or not self.current_adapter:
            return None
        if self.current_adapter.supports_cross_database_queries:
            return database
        return None

    def _clear_query_target_database(self: AppProtocol) -> None:
        """Clear any pending per-query database override."""
        if hasattr(self, "_query_target_database"):
            self._query_target_database = None

    def action_new_connection(self: AppProtocol) -> None:
        from ..screens import ConnectionScreen

        self._set_connection_screen_footer()
        self.push_screen(ConnectionScreen(), self._wrap_connection_result)

    def action_edit_connection(self: AppProtocol) -> None:
        from ..screens import ConnectionScreen

        node = self.object_tree.cursor_node

        if not node:
            return

        config = self._get_connection_config_from_node(node)
        if not config:
            return

        self._set_connection_screen_footer()
        self.push_screen(ConnectionScreen(config, editing=True), self._wrap_connection_result)

    def _set_connection_screen_footer(self: AppProtocol) -> None:
        from ...widgets import ContextFooter

        try:
            footer = self.query_one(ContextFooter)
        except Exception:
            return
        footer.set_bindings([], [])

    def _wrap_connection_result(self: AppProtocol, result: tuple | None) -> None:
        self._update_footer_bindings()
        self.handle_connection_result(result)

    def handle_connection_result(self: AppProtocol, result: tuple | None) -> None:
        from ...config import load_settings, save_connections, save_settings
        from ...services.credentials import (
            ALLOW_PLAINTEXT_CREDENTIALS_SETTING,
            is_keyring_usable,
            reset_credentials_service,
        )
        from ..screens import ConfirmScreen

        if not result:
            return

        action, config = result[0], result[1]
        original_name = result[2] if len(result) > 2 else None

        if action == "save":
            def do_save(with_config, orig_name=None) -> None:  # noqa: ANN001
                # When editing, remove by original name to properly update renamed connections
                if orig_name:
                    self.connections = [c for c in self.connections if c.name != orig_name]
                # Also remove by new name to handle overwrites/duplicates
                self.connections = [c for c in self.connections if c.name != with_config.name]
                self.connections.append(with_config)
                if getattr(self, "_mock_profile", None):
                    self.notify("Mock mode: connection changes are not persisted")
                else:
                    save_connections(self.connections)
                self.refresh_tree()
                self.notify(f"Connection '{with_config.name}' saved")

            needs_password_persist = bool(getattr(config, "password", "") or getattr(config, "ssh_password", ""))
            if not getattr(self, "_mock_profile", None) and needs_password_persist and not is_keyring_usable():
                settings = load_settings()
                allow_plaintext = settings.get(ALLOW_PLAINTEXT_CREDENTIALS_SETTING)

                if allow_plaintext is True:
                    reset_credentials_service()
                    do_save(config, original_name)
                    return

                if allow_plaintext is False:
                    config.password = ""
                    config.ssh_password = ""
                    do_save(config, original_name)
                    self.notify("Keyring unavailable: passwords will be prompted when needed", severity="warning")
                    return

                def on_confirm(confirmed: bool | None) -> None:
                    settings2 = load_settings()
                    if confirmed is True:
                        settings2[ALLOW_PLAINTEXT_CREDENTIALS_SETTING] = True
                        save_settings(settings2)
                        reset_credentials_service()
                        do_save(config, original_name)
                        self.notify("Saved passwords as plaintext in ~/.sqlit/ (0600)", severity="warning")
                        return

                    settings2[ALLOW_PLAINTEXT_CREDENTIALS_SETTING] = False
                    save_settings(settings2)
                    config.password = ""
                    config.ssh_password = ""
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

    def action_duplicate_connection(self: AppProtocol) -> None:
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

    def action_delete_connection(self: AppProtocol) -> None:
        from ..screens import ConfirmScreen

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

    def _do_delete_connection(self: AppProtocol, config: ConnectionConfig) -> None:
        from ...config import save_connections

        self.connections = [c for c in self.connections if c.name != config.name]
        if getattr(self, "_mock_profile", None):
            self.notify("Mock mode: connection changes are not persisted")
        else:
            save_connections(self.connections)
        self.refresh_tree()
        self.notify(f"Connection '{config.name}' deleted")

    def _handle_install_confirmation(self: AppProtocol, confirmed: bool | None, error: Any) -> None:
        from ...db.adapters.base import _create_driver_import_error_hint
        from ...services.installer import Installer
        from ..screens import ErrorScreen

        if confirmed is True:
            installer = Installer(self)  # self is the App instance
            self.call_next(installer.install, error)  # Schedule the async install method
        elif confirmed is False:
            hint = _create_driver_import_error_hint(error.driver_name, error.extra_name, error.package_name)
            self.push_screen(ErrorScreen("Manual Installation Required", hint))
        else:
            return

    def action_connect_selected(self: AppProtocol) -> None:
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

    def action_show_connection_picker(self: AppProtocol) -> None:
        from ..screens import ConnectionPickerScreen

        self.push_screen(
            ConnectionPickerScreen(self.connections),
            self._handle_connection_picker_result,
        )

    def _handle_connection_picker_result(self: AppProtocol, result: Any) -> None:
        if result is None:
            return

        # Handle special "new connection" action
        if result == "__new_connection__":
            self.action_new_connection()
            return

        result_kind = getattr(result, "get_result_kind", None)
        if callable(result_kind) and result_kind() == "docker":
            self._handle_docker_container_result(result)
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

    def _handle_docker_container_result(self: AppProtocol, result: DockerConnectionResult) -> None:
        """Handle a Docker container selection from the connection picker."""
        from ...services.docker_detector import container_to_connection_config

        container = result.container
        config = container_to_connection_config(container)

        # Try to find matching saved connection to select in tree
        matching_config = self._find_matching_saved_connection(container)
        if matching_config:
            # Select the saved connection in tree
            for node in self.object_tree.root.children:
                node_config = self._get_connection_config_from_node(node)
                if node_config and node_config.name == matching_config.name:
                    self.object_tree.select_node(node)
                    break
            # Use the saved config (has the saved name)
            config = matching_config

        # Connect directly (saving is handled in the picker itself)
        # Don't disconnect here - we'll disconnect only after successful connection
        self.connect_to_server(config)

    def _find_matching_saved_connection(self: AppProtocol, container: DetectedContainer) -> ConnectionConfig | None:
        """Find a saved connection that matches a Docker container."""
        for conn in self.connections:
            # Match by host:port and db_type
            if (
                conn.db_type == container.db_type
                and conn.server in ("localhost", "127.0.0.1", container.host)
                and conn.port == str(container.port)
            ):
                return conn
            # Also match by name
            if conn.name == container.container_name:
                return conn
        return None
