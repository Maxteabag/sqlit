"""Connection management mixin for SSMSTUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..protocols import AppProtocol
from ..tree_nodes import ConnectionNode

if TYPE_CHECKING:
    from ...config import ConnectionConfig
    from ...db import DatabaseAdapter


def _needs_db_password(config: ConnectionConfig) -> bool:
    """Check if the connection needs a database password prompt.

    Returns True if password is None (not set) and the database type uses passwords.
    Note: Empty string "" means explicitly set to empty (no prompt needed).
    """
    from ...db.providers import is_file_based

    # File-based databases (SQLite, DuckDB) don't need passwords
    if is_file_based(config.db_type):
        return False

    # Check if password is not set (None means prompt needed)
    return config.password is None


def _needs_ssh_password(config: ConnectionConfig) -> bool:
    """Check if the connection needs an SSH password prompt.

    Returns True if SSH is enabled with password auth and password is None (not set).
    Note: Empty string "" means explicitly set to empty (no prompt needed).
    """
    if not config.ssh_enabled:
        return False

    if config.ssh_auth_type != "password":
        return False

    return config.ssh_password is None


class ConnectionMixin:
    """Mixin providing connection management functionality."""

    current_config: ConnectionConfig | None = None
    current_adapter: DatabaseAdapter | None = None

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

    def _do_connect(self: AppProtocol, config: ConnectionConfig) -> None:
        from ...services import ConnectionSession

        if hasattr(self, "_session") and self._session:
            self._session.close()
            self._session = None
            self.current_connection = None
            self.current_config = None
            self.current_adapter = None
            self.current_ssh_tunnel = None
            self.refresh_tree()

        self._connection_failed = False

        create_session = self._session_factory or ConnectionSession.create

        def work() -> ConnectionSession:
            return create_session(config)

        def on_success(session: ConnectionSession) -> None:
            self._connection_failed = False
            self._session = session
            self.current_connection = session.connection
            self.current_config = config
            self.current_adapter = session.adapter
            self.current_ssh_tunnel = session.tunnel

            self.refresh_tree()
            self._load_schema_cache()
            self._update_status_bar()

        def on_error(error: Exception) -> None:
            from ...config import save_connections
            from ...db.exceptions import MissingDriverError, MissingODBCDriverError
            from ...terminal import run_in_terminal
            from ..screens import ConfirmScreen, DriverSetupScreen, ErrorScreen, MessageScreen

            self._connection_failed = True
            self._update_status_bar()

            if isinstance(error, MissingDriverError):
                from ...services.installer import Installer
                from ..screens import PackageSetupScreen

                self.push_screen(
                    PackageSetupScreen(error, on_install=lambda err: Installer(self).install(err)),
                )
            elif isinstance(error, MissingODBCDriverError):

                def on_confirm(confirmed: bool | None) -> None:
                    if confirmed is not True:
                        self.push_screen(
                            MessageScreen(
                                "Missing ODBC driver",
                                (
                                    "SQL Server requires an ODBC driver.\n\n"
                                    "Open connection settings (Advanced) to configure drivers."
                                ),
                            )
                        )
                        return

                    def on_driver_result(result: Any) -> None:
                        if not result:
                            return
                        action = result[0]
                        if action == "select":
                            driver = result[1]
                            config.driver = driver
                            for i, c in enumerate(self.connections):
                                if c.name == config.name:
                                    self.connections[i] = config
                                    break
                            save_connections(self.connections)
                            self.call_later(lambda: self.connect_to_server(config))
                            return
                        if action == "install":
                            commands = result[1]
                            res = run_in_terminal(commands)
                            if res.success:
                                self.push_screen(
                                    MessageScreen(
                                        "Driver install",
                                        "Installation started in a new terminal.\n\nPlease restart to apply.",
                                    )
                                )
                            else:
                                self.push_screen(
                                    MessageScreen(
                                        "Couldn't install automatically",
                                        "Couldn't install automatically, please install manually.",
                                    ),
                                    lambda _=None: self.push_screen(
                                        DriverSetupScreen(error.installed_drivers), on_driver_result
                                    ),
                                )

                    self.push_screen(DriverSetupScreen(error.installed_drivers), on_driver_result)

                self.push_screen(
                    ConfirmScreen(
                        "Missing ODBC driver",
                        "SQL Server requires an ODBC driver.\n\nOpen driver setup now?",
                    ),
                    on_confirm,
                )
            else:
                self.push_screen(ErrorScreen("Connection Failed", str(error)))

        def do_work() -> None:
            try:
                session = work()
                self.call_from_thread(on_success, session)
            except Exception as e:
                self.call_from_thread(on_error, e)

        self.run_worker(do_work, name=f"connect-{config.name}", thread=True, exclusive=True)

    def _disconnect_silent(self: AppProtocol) -> None:
        if hasattr(self, "_session") and self._session:
            self._session.close()
            self._session = None

        self.current_connection = None
        self.current_config = None
        self.current_adapter = None
        self.current_ssh_tunnel = None

    def action_disconnect(self: AppProtocol) -> None:
        """Disconnect from current database."""
        if self.current_connection:
            self._disconnect_silent()

            self.status_bar.update("Disconnected")

            self.refresh_tree()
            self.notify("Disconnected")

    def action_new_connection(self: AppProtocol) -> None:
        from ..screens import ConnectionScreen

        self._set_connection_screen_footer()
        self.push_screen(ConnectionScreen(), self._wrap_connection_result)

    def action_edit_connection(self: AppProtocol) -> None:
        from ..screens import ConnectionScreen

        node = self.object_tree.cursor_node

        if not node or not node.data:
            return

        data = node.data
        if not isinstance(data, ConnectionNode):
            return

        self._set_connection_screen_footer()
        self.push_screen(ConnectionScreen(data.config, editing=True), self._wrap_connection_result)

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

        if not node or not node.data:
            return

        data = node.data
        if not isinstance(data, ConnectionNode):
            return

        config = data.config

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

        if not node or not node.data:
            return

        data = node.data
        if not isinstance(data, ConnectionNode):
            return

        config = data.config

        if self.current_config and self.current_config.name == config.name:
            self.notify("Disconnect first before deleting", severity="warning")
            return

        self.push_screen(
            ConfirmScreen(f"Delete '{config.name}'?"),
            lambda confirmed: self._do_delete_connection(config) if confirmed else None,
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

        if not node or not node.data:
            return

        data = node.data
        if isinstance(data, ConnectionNode):
            config = data.config
            if self.current_config and self.current_config.name == config.name:
                return
            if self.current_connection:
                self._disconnect_silent()
            self.connect_to_server(config)

    def action_show_connection_picker(self: AppProtocol) -> None:
        from ..screens import ConnectionPickerScreen

        self.push_screen(
            ConnectionPickerScreen(self.connections),
            self._handle_connection_picker_result,
        )

    def _handle_connection_picker_result(self: AppProtocol, result: str | None) -> None:
        if result is None:
            return

        config = next((c for c in self.connections if c.name == result), None)
        if config:
            for node in self.object_tree.root.children:
                if isinstance(node.data, ConnectionNode) and node.data.config.name == result:
                    self.object_tree.select_node(node)
                    break

            if self.current_config and self.current_config.name == config.name:
                self.notify(f"Already connected to {config.name}")
                return
            if self.current_connection:
                self._disconnect_silent()
            self.connect_to_server(config)
