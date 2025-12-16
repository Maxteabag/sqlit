"""Connection management mixin for SSMSTUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..protocols import AppProtocol
from ..tree_nodes import ConnectionNode

if TYPE_CHECKING:
    from ...config import ConnectionConfig
    from ...db import DatabaseAdapter


class ConnectionMixin:
    """Mixin providing connection management functionality."""

    current_config: ConnectionConfig | None = None
    current_adapter: DatabaseAdapter | None = None

    def connect_to_server(self: AppProtocol, config: ConnectionConfig) -> None:
        """Connect to a database (async, non-blocking)."""
        from ...services import ConnectionSession

        # Close any existing session first
        if hasattr(self, "_session") and self._session:
            self._session.close()
            self._session = None
            self.current_connection = None
            self.current_config = None
            self.current_adapter = None
            self.current_ssh_tunnel = None
            self.refresh_tree()

        # Reset connection failed state
        self._connection_failed = False

        # Use injected factory or default
        create_session = self._session_factory or ConnectionSession.create

        def work() -> ConnectionSession:
            """Create connection in worker thread."""
            return create_session(config)

        def on_success(session: ConnectionSession) -> None:
            """Handle successful connection on main thread."""
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
            """Handle connection failure on main thread."""
            from ...db.exceptions import MissingDriverError
            from ..screens import ConfirmScreen, ErrorScreen

            self._connection_failed = True
            self._update_status_bar()

            if isinstance(error, MissingDriverError):
                self.push_screen(
                    ConfirmScreen(
                        "Missing driver",
                        f"This connection requires the {error.driver_name} driver.\n\nInstall it now?",
                        yes_label="Install now",
                        no_label="Manual steps",
                    ),
                    lambda confirmed: self._handle_install_confirmation(confirmed, error),
                )
            else:
                self.push_screen(ErrorScreen("Connection Failed", str(error)))

        def do_work() -> None:
            """Worker function with error handling."""
            try:
                session = work()
                self.call_from_thread(on_success, session)
            except Exception as e:
                self.call_from_thread(on_error, e)

        self.run_worker(do_work, name=f"connect-{config.name}", thread=True, exclusive=True)

    def _disconnect_silent(self: AppProtocol) -> None:
        """Disconnect from current database without notification."""
        # Use session's close method for proper cleanup
        if hasattr(self, "_session") and self._session:
            self._session.close()
            self._session = None

        # Clear instance variables
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
        """Show new connection dialog."""
        from ..screens import ConnectionScreen

        self._set_connection_screen_footer()
        self.push_screen(ConnectionScreen(), self._wrap_connection_result)

    def action_edit_connection(self: AppProtocol) -> None:
        """Edit the selected connection."""
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
        """Set footer bindings for connection screen."""
        from ...widgets import ContextFooter

        try:
            footer = self.query_one(ContextFooter)
        except Exception:
            return
        footer.set_bindings([], [])

    def _wrap_connection_result(self: AppProtocol, result: tuple | None) -> None:
        """Wrapper to restore footer after connection dialog."""
        self._update_footer_bindings()
        self.handle_connection_result(result)

    def handle_connection_result(self: AppProtocol, result: tuple | None) -> None:
        """Handle result from connection dialog."""
        from ...config import save_connections

        if not result:
            return

        action, config = result

        if action == "save":
            self.connections = [c for c in self.connections if c.name != config.name]
            self.connections.append(config)
            if getattr(self, "_mock_profile", None):
                self.notify("Mock mode: connection changes are not persisted")
            else:
                save_connections(self.connections)
            self.refresh_tree()
            self.notify(f"Connection '{config.name}' saved")

    def action_duplicate_connection(self: AppProtocol) -> None:
        """Duplicate the selected connection."""
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
        """Delete the selected connection."""
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
        """Actually delete the connection after confirmation."""
        from ...config import save_connections

        self.connections = [c for c in self.connections if c.name != config.name]
        if getattr(self, "_mock_profile", None):
            self.notify("Mock mode: connection changes are not persisted")
        else:
            save_connections(self.connections)
        self.refresh_tree()
        self.notify(f"Connection '{config.name}' deleted")

    def _handle_install_confirmation(self: AppProtocol, confirmed: bool | None, error: Any) -> None:
        """Handle the result of the driver install confirmation."""
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
            # Cancelled.
            return

    def action_connect_selected(self: AppProtocol) -> None:
        """Connect to the selected connection."""
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
        """Show connection picker dialog."""
        from ..screens import ConnectionPickerScreen

        self.push_screen(
            ConnectionPickerScreen(self.connections),
            self._handle_connection_picker_result,
        )

    def _handle_connection_picker_result(self: AppProtocol, result: str | None) -> None:
        """Handle connection picker selection."""
        if result is None:
            return

        config = next((c for c in self.connections if c.name == result), None)
        if config:
            # Select the connection node in the tree
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
