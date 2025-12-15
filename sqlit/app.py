"""Main Textual application for sqlit."""

from __future__ import annotations

from typing import Any

try:
    import pyodbc

    PYODBC_AVAILABLE = True
except ImportError:
    PYODBC_AVAILABLE = False

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import DataTable, Static, TextArea, Tree

from .config import (
    ConnectionConfig,
    load_connections,
    load_settings,
    save_settings,
)
from .db import DatabaseAdapter
from .ui.mixins import (
    AutocompleteMixin,
    ConnectionMixin,
    QueryMixin,
    ResultsMixin,
    TreeMixin,
    UINavigationMixin,
)
from .widgets import AutocompleteDropdown, ContextFooter, VimMode


class SSMSTUI(
    TreeMixin,
    ConnectionMixin,
    QueryMixin,
    AutocompleteMixin,
    ResultsMixin,
    UINavigationMixin,
    App,
):
    """Main SSMS TUI application."""

    TITLE = "sqlit"

    CSS = """
    Screen {
        background: $surface;
    }

    DataTable.flash-cell:focus > .datatable--cursor,
    DataTable.flash-row:focus > .datatable--cursor,
    DataTable.flash-all:focus > .datatable--cursor {
        background: $success;
        color: $background;
        text-style: bold;
    }

    DataTable.flash-all {
        border: solid $success;
    }

    Screen.results-fullscreen #sidebar {
        display: none;
    }

    Screen.results-fullscreen #query-area {
        display: none;
    }

    Screen.results-fullscreen #results-area {
        height: 1fr;
    }

    Screen.query-fullscreen #sidebar {
        display: none;
    }

    Screen.query-fullscreen #results-area {
        display: none;
    }

    Screen.query-fullscreen #query-area {
        height: 1fr;
        border-bottom: none;
    }

    Screen.explorer-fullscreen #main-panel {
        display: none;
    }

    Screen.explorer-fullscreen #sidebar {
        width: 1fr;
        border-right: none;
    }

    Screen.explorer-hidden #sidebar {
        display: none;
    }

    #main-container {
        width: 100%;
        height: 100%;
    }

    #content {
        height: 1fr;
    }

    #sidebar {
        width: 35;
        border-right: solid $primary;
        padding: 1;
    }

    #object-tree {
        height: 1fr;
    }

    #main-panel {
        width: 1fr;
    }

    #query-area {
        height: 50%;
        border-bottom: solid $primary;
        padding: 1;
    }

    #query-input {
        height: 1fr;
    }

    #results-area {
        height: 50%;
        padding: 1;
    }

    #results-table {
        height: 1fr;
    }

    #status-bar {
        height: 1;
        background: $surface-darken-1;
        padding: 0 1;
    }

    .section-label {
        height: 1;
        color: $text-muted;
        padding: 0 1;
        margin-bottom: 1;
    }

    .section-label.active {
        color: $primary;
        text-style: bold;
    }

    #autocomplete-dropdown {
        layer: autocomplete;
        position: absolute;
        display: none;
    }

    #autocomplete-dropdown.visible {
        display: block;
    }
    """

    LAYERS = ["autocomplete"]

    BINDINGS = [
        # Leader combo bindings (checked first when _leader_pending is True)
        Binding("e", "leader_toggle_explorer", show=False),
        Binding("f", "leader_fullscreen", show=False),
        Binding("h", "leader_help", show=False),
        Binding("t", "leader_theme", show=False),
        Binding("q", "leader_quit", show=False),
        Binding("c", "leader_connect", show=False),
        Binding("x", "leader_disconnect", show=False),
        Binding("z", "leader_cancel", show=False),
        # Regular bindings
        Binding("n", "new_connection", "New", show=False),
        Binding("s", "select_table", "Select", show=False),
        Binding("R", "refresh_tree", "Refresh", show=False),
        Binding("f", "refresh_tree", "Refresh", show=False),
        Binding("e", "edit_connection", "Edit", show=False),
        Binding("d", "delete_connection", "Delete", show=False),
        Binding("D", "duplicate_connection", "Duplicate", show=False),
        Binding("delete", "delete_connection", "Delete", show=False),
        Binding("x", "disconnect", "Disconnect", show=False),
        Binding("space", "leader_key", "Commands", show=False, priority=True),
        Binding("ctrl+q", "quit", "Quit", show=False),
        Binding("question_mark", "show_help", "Help", show=False),
        Binding("e", "focus_explorer", "Explorer", show=False),
        Binding("q", "focus_query", "Query", show=False),
        Binding("r", "focus_results", "Results", show=False),
        Binding("i", "enter_insert_mode", "Insert", show=False),
        Binding("escape", "exit_insert_mode", "Normal", show=False),
        Binding("enter", "execute_query", "Execute", show=False),
        Binding("f5", "execute_query_insert", "Execute", show=False),
        Binding("d", "clear_query", "Clear", show=False),
        Binding("n", "new_query", "New", show=False),
        Binding("h", "show_history", "History", show=False),
        Binding("z", "collapse_tree", "Collapse", show=False),
        Binding("v", "view_cell", "View cell", show=False),
        Binding("y", "copy_cell", "Copy cell", show=False),
        Binding("Y", "copy_row", "Copy row", show=False),
        Binding("a", "copy_results", "Copy results", show=False),
        Binding("ctrl+c", "cancel_operation", "Cancel", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.connections: list[ConnectionConfig] = []
        self.current_connection: Any | None = None
        self.current_config: ConnectionConfig | None = None
        self.current_adapter: DatabaseAdapter | None = None
        self.current_ssh_tunnel: Any | None = None
        self.vim_mode: VimMode = VimMode.NORMAL
        self._expanded_paths: set[str] = set()
        self._loading_nodes: set[str] = set()
        self._session: Any | None = None
        self._schema_cache: dict = {
            "tables": [],
            "views": [],
            "columns": {},
            "procedures": [],
        }
        self._autocomplete_visible: bool = False
        self._autocomplete_items: list[str] = []
        self._autocomplete_index: int = 0
        self._autocomplete_filter: str = ""
        self._autocomplete_just_applied: bool = False
        self._last_result_columns: list[str] = []
        self._last_result_rows: list[tuple] = []
        self._last_result_row_count: int = 0
        self._internal_clipboard: str = ""
        self._fullscreen_mode: str = "none"
        self._last_notification: str = ""
        self._last_notification_severity: str = "information"
        self._last_notification_time: str = ""
        self._notification_timer = None
        self._notification_history: list = []
        self._connection_failed: bool = False
        self._leader_timer = None
        self._leader_pending: bool = False
        self._query_worker = None
        self._query_executing: bool = False
        self._cancellable_query: Any | None = None
        self._spinner_index: int = 0
        self._spinner_timer = None
        # Schema indexing state
        self._schema_indexing: bool = False
        self._schema_worker = None
        self._schema_spinner_index: int = 0
        self._schema_spinner_timer = None
        self._table_metadata: dict = {}
        self._columns_loading: set[str] = set()

    @property
    def object_tree(self) -> Tree:
        return self.query_one("#object-tree", Tree)

    @property
    def query_input(self) -> TextArea:
        return self.query_one("#query-input", TextArea)

    @property
    def results_table(self) -> DataTable:
        return self.query_one("#results-table", DataTable)

    @property
    def sidebar(self):
        return self.query_one("#sidebar")

    @property
    def main_panel(self):
        return self.query_one("#main-panel")

    @property
    def query_area(self):
        return self.query_one("#query-area")

    @property
    def results_area(self):
        return self.query_one("#results-area")

    @property
    def status_bar(self) -> Static:
        return self.query_one("#status-bar", Static)

    @property
    def autocomplete_dropdown(self):
        from .widgets import AutocompleteDropdown
        return self.query_one("#autocomplete-dropdown", AutocompleteDropdown)

    def push_screen(self, screen, callback=None, wait_for_dismiss: bool = False):
        """Override push_screen to hide footer when showing modal dialogs."""
        from textual.screen import ModalScreen

        if isinstance(screen, ModalScreen):
            self._hide_footer()
        return super().push_screen(screen, callback, wait_for_dismiss=wait_for_dismiss)

    def pop_screen(self):
        """Override pop_screen to restore footer when closing modal dialogs."""
        result = super().pop_screen()
        # Check if we're back to the main screen (no modal screens)
        if not any(
            hasattr(s, "__class__") and "ModalScreen" in str(s.__class__.__mro__)
            for s in self.screen_stack[1:]  # Skip the base screen
        ):
            self._show_footer()
        return result

    def _hide_footer(self) -> None:
        """Clear the footer content when showing dialogs."""
        try:
            footer = self.query_one(ContextFooter)
            footer.set_bindings([], [])
        except Exception:
            pass

    def _show_footer(self) -> None:
        """Restore the footer content after closing dialogs."""
        self._update_footer_bindings()

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        """Only allow actions when their context is active."""
        # Leader combo actions only work when _leader_pending is True
        if action.startswith("leader_") and action != "leader_key":
            if getattr(self, "_leader_pending", False):
                # Cancel timer and clear pending state
                if hasattr(self, "_leader_timer") and self._leader_timer is not None:
                    self._leader_timer.stop()
                    self._leader_timer = None
                self._leader_pending = False
                return True
            return False

        # Block most actions when waiting for leader combo
        if getattr(self, "_leader_pending", False):
            # Only allow leader_key action during leader pending
            if action != "leader_key":
                return False

        tree_focused = self.object_tree.has_focus
        query_focused = self.query_input.has_focus
        results_focused = self.results_table.has_focus
        in_insert_mode = self.vim_mode == VimMode.INSERT

        node = self.object_tree.cursor_node
        node_type = None
        is_root = node == self.object_tree.root if node else False
        if node and node.data:
            node_type = node.data[0]

        if action == "enter_insert_mode":
            return query_focused and not in_insert_mode
        elif action == "exit_insert_mode":
            return in_insert_mode

        if in_insert_mode:
            if action in (
                "quit",
                "exit_insert_mode",
                "execute_query_insert",
            ):
                return True
            return False

        if action == "new_connection":
            return tree_focused
        elif action == "refresh_tree":
            return tree_focused
        elif action == "collapse_tree":
            return tree_focused
        elif action == "edit_connection":
            return tree_focused and node_type == "connection"
        elif action == "delete_connection":
            return tree_focused and node_type == "connection"
        elif action == "connect_selected":
            if not tree_focused or node_type != "connection":
                return False
            config = node.data[1] if node and node.data else None
            if not self.current_connection:
                return True
            return config and self.current_config and config.name != self.current_config.name
        elif action == "disconnect":
            return (
                tree_focused
                and node_type == "connection"
                and self.current_connection is not None
            )
        elif action == "select_table":
            return tree_focused and node_type in ("table", "view")
        elif action == "execute_query":
            return query_focused or results_focused
        elif action == "execute_query_insert":
            return query_focused
        elif action in ("clear_query", "new_query"):
            return query_focused and self.vim_mode == VimMode.NORMAL
        elif action == "show_history":
            return query_focused and self.vim_mode == VimMode.NORMAL and self.current_config is not None
        elif action == "focus_explorer":
            if tree_focused and node_type == "connection":
                return False
            return True
        elif action in ("focus_query", "focus_results"):
            return True
        elif action == "toggle_fullscreen":
            # Don't allow toggle_fullscreen when tree focused (f is refresh there)
            return not tree_focused
        elif action == "test_connections":
            return True
        elif action in ("view_cell", "copy_cell", "copy_row", "copy_results"):
            return results_focused
        elif action in (
            "quit",
            "show_help",
            "leader_key",
            "toggle_dark",
        ):
            return True

        return True

    def compose(self) -> ComposeResult:
        with Vertical(id="main-container"):
            with Horizontal(id="content"):
                with Vertical(id="sidebar"):
                    yield Static(
                        r"\[e] Object Explorer", classes="section-label", id="label-explorer"
                    )
                    tree = Tree("Servers", id="object-tree")
                    tree.show_root = False
                    tree.guide_depth = 2
                    yield tree

                with Vertical(id="main-panel"):
                    with Container(id="query-area"):
                        yield Static(
                            r"\[q] Query", classes="section-label", id="label-query"
                        )
                        yield TextArea(
                            "",
                            language="sql",
                            id="query-input",
                            read_only=True,
                        )
                        yield AutocompleteDropdown(id="autocomplete-dropdown")

                    with Container(id="results-area"):
                        yield Static(
                            r"\[r] Results", classes="section-label", id="label-results"
                        )
                        yield DataTable(id="results-table", zebra_stripes=True)

            yield Static("Not connected", id="status-bar")

        yield ContextFooter()

    def on_mount(self) -> None:
        """Initialize the app."""
        if not PYODBC_AVAILABLE:
            self.notify(
                "pyodbc not installed. Run: pip install pyodbc",
                severity="warning",
                timeout=10,
            )

        settings = load_settings()
        if "theme" in settings:
            try:
                self.theme = settings["theme"]
            except Exception:
                self.theme = "tokyo-night"
        else:
            self.theme = "tokyo-night"

        settings = load_settings()
        self._expanded_paths = set(settings.get("expanded_nodes", []))

        self.connections = load_connections()
        self.refresh_tree()
        self._update_footer_bindings()

        self.object_tree.focus()
        # Move cursor to first node if available
        if self.object_tree.root.children:
            self.object_tree.cursor_line = 0
        self._update_section_labels()

        # Check for ODBC drivers
        self._check_drivers()

    def _check_drivers(self) -> None:
        """Check if ODBC drivers are installed and show setup if needed."""
        has_mssql = any(c.db_type == "mssql" for c in self.connections)
        if not has_mssql:
            return

        if not PYODBC_AVAILABLE:
            return

        from .drivers import get_installed_drivers

        installed = get_installed_drivers()
        if not installed:
            self.call_later(self._show_driver_setup)

    def _show_driver_setup(self) -> None:
        """Show the driver setup screen."""
        from .drivers import get_installed_drivers
        from .ui.screens import DriverSetupScreen

        installed = get_installed_drivers()
        self.push_screen(DriverSetupScreen(installed), self._handle_driver_result)

    def _handle_driver_result(self, result) -> None:
        """Handle result from driver setup screen."""
        if not result:
            return

        action = result[0]
        if action == "select":
            driver = result[1]
            self.notify(f"Selected driver: {driver}")
        elif action == "install":
            commands = result[1]
            self._run_driver_install(commands)

    def _run_driver_install(self, commands: list[str]) -> None:
        """Run driver installation commands."""
        import subprocess

        self.notify("Running installation commands...", timeout=3)

        full_command = " && ".join(commands)

        try:
            import shutil

            if shutil.which("gnome-terminal"):
                subprocess.Popen([
                    "gnome-terminal", "--", "bash", "-c",
                    f'{full_command}; echo ""; echo "Press Enter to close..."; read'
                ])
            elif shutil.which("konsole"):
                subprocess.Popen([
                    "konsole", "-e", "bash", "-c",
                    f'{full_command}; echo ""; echo "Press Enter to close..."; read'
                ])
            elif shutil.which("xterm"):
                subprocess.Popen([
                    "xterm", "-e", "bash", "-c",
                    f'{full_command}; echo ""; echo "Press Enter to close..."; read'
                ])
            elif shutil.which("open"):  # macOS
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
                    f.write("#!/bin/bash\n")
                    f.write(full_command + "\n")
                    f.write('echo ""\necho "Press Enter to close..."\nread\n')
                    script_path = f.name
                import os
                os.chmod(script_path, 0o755)
                subprocess.Popen(["open", "-a", "Terminal", script_path])
            else:
                self.notify(
                    "No terminal found. Run these commands manually:\n" + full_command,
                    severity="warning",
                    timeout=15,
                )
                return

            self.notify(
                "Installation started in new terminal. Restart sqlit when done.",
                timeout=10,
            )
        except Exception as e:
            self.notify(f"Failed to start installation: {e}", severity="error")

    def watch_theme(self, old_theme: str, new_theme: str) -> None:
        """Save theme whenever it changes."""
        settings = load_settings()
        settings["theme"] = new_theme
        save_settings(settings)
