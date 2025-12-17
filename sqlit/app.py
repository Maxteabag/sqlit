"""Main Textual application for sqlit."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import DataTable, Static, TextArea, Tree
from textual.worker import Worker

from .config import (
    ConnectionConfig,
    load_connections,
    load_settings,
    save_settings,
)
from .db import DatabaseAdapter
from .mocks import MockProfile
from .state_machine import (
    UIStateMachine,
    get_leader_bindings,
)
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
        # Leader combo bindings - generated from keymap provider
        *get_leader_bindings(),
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

    def __init__(self, mock_profile: MockProfile | None = None):
        super().__init__()
        self._mock_profile = mock_profile
        self._debug_mode = os.environ.get("SQLIT_DEBUG") == "1"
        self._startup_mark = self._parse_startup_mark(os.environ.get("SQLIT_STARTUP_MARK"))
        self._startup_init_time = time.perf_counter()
        self._launch_ms: float | None = None
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
        self._notification_timer: Timer | None = None
        self._notification_history: list = []
        self._connection_failed: bool = False
        self._leader_timer: Timer | None = None
        self._leader_pending: bool = False
        self._query_worker: Worker[Any] | None = None
        self._query_executing: bool = False
        self._cancellable_query: Any | None = None
        self._spinner_index: int = 0
        self._spinner_timer: Timer | None = None
        # Schema indexing state
        self._schema_indexing: bool = False
        self._schema_worker: Worker[Any] | None = None
        self._schema_spinner_index: int = 0
        self._schema_spinner_timer: Timer | None = None
        self._table_metadata: dict = {}
        self._columns_loading: set[str] = set()
        self._state_machine = UIStateMachine()
        self._session_factory: Any | None = None

        if mock_profile:
            self._session_factory = self._create_mock_session_factory(mock_profile)

    def _create_mock_session_factory(self, profile: MockProfile) -> Any:
        """Create a session factory that uses mock adapters."""
        from .services import ConnectionSession

        def mock_adapter_factory(db_type: str) -> Any:
            """Return mock adapter for the given db type."""
            return profile.get_adapter(db_type)

        def mock_tunnel_factory(config: Any) -> Any:
            """Return no tunnel for mock connections."""
            return None, config.server, int(config.port or "0")

        def factory(config: Any) -> Any:
            return ConnectionSession.create(
                config,
                adapter_factory=mock_adapter_factory,
                tunnel_factory=mock_tunnel_factory,
            )

        return factory

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
    def sidebar(self) -> Any:
        return self.query_one("#sidebar")

    @property
    def main_panel(self) -> Any:
        return self.query_one("#main-panel")

    @property
    def query_area(self) -> Any:
        return self.query_one("#query-area")

    @property
    def results_area(self) -> Any:
        return self.query_one("#results-area")

    @property
    def status_bar(self) -> Static:
        return self.query_one("#status-bar", Static)

    @property
    def autocomplete_dropdown(self) -> Any:
        from .widgets import AutocompleteDropdown

        return self.query_one("#autocomplete-dropdown", AutocompleteDropdown)

    def push_screen(
        self,
        screen: Any,
        callback: Callable[[Any], None] | Callable[[Any], Awaitable[None]] | None = None,
        wait_for_dismiss: bool = False,
    ) -> Any:
        """Override push_screen to update footer when screen changes."""
        if wait_for_dismiss:
            future = super().push_screen(screen, callback, wait_for_dismiss=True)
            self._update_footer_bindings()
            return future
        mount = super().push_screen(screen, callback, wait_for_dismiss=False)
        self._update_footer_bindings()
        return mount

    def pop_screen(self) -> Any:
        """Override pop_screen to update footer when screen changes."""
        result = super().pop_screen()
        self._update_footer_bindings()
        return result

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        """Check if an action is allowed in the current state.

        This method is pure - it only checks, never mutates state.
        State transitions happen in the action methods themselves.
        """
        return self._state_machine.check_action(self, action)

    def _compute_restart_argv(self) -> list[str]:
        """Compute a best-effort argv to restart the app."""
        # Linux provides the most reliable answer via /proc.
        try:
            cmdline_path = "/proc/self/cmdline"
            if os.path.exists(cmdline_path):
                raw = open(cmdline_path, "rb").read()
                parts = [p.decode(errors="surrogateescape") for p in raw.split(b"\0") if p]
                if parts:
                    return parts
        except Exception:
            pass

        # Fallback: sys.argv (good enough for most invocations).
        argv = [sys.argv[0], *sys.argv[1:]] if sys.argv else []
        if argv:
            return argv
        return [sys.executable]

    def restart(self) -> None:
        """Restart the current process in-place."""
        argv = getattr(self, "_restart_argv", None) or self._compute_restart_argv()
        exe = argv[0]
        # execv doesn't search PATH; use execvp for bare commands (e.g. "sqlit").
        if os.sep in exe:
            os.execv(exe, argv)
        else:
            os.execvp(exe, argv)

    def compose(self) -> ComposeResult:
        with Vertical(id="main-container"):
            with Horizontal(id="content"):
                with Vertical(id="sidebar"):
                    yield Static(r"\[E] Explorer", classes="section-label", id="label-explorer")
                    tree: Tree[Any] = Tree("Servers", id="object-tree")
                    tree.show_root = False
                    tree.guide_depth = 2
                    yield tree

                with Vertical(id="main-panel"):
                    with Container(id="query-area"):
                        yield Static(r"\[q] Query", classes="section-label", id="label-query")
                        yield TextArea(
                            "",
                            language="sql",
                            id="query-input",
                            read_only=True,
                        )
                        yield AutocompleteDropdown(id="autocomplete-dropdown")

                    with Container(id="results-area"):
                        yield Static(r"\[r] Results", classes="section-label", id="label-results")
                        yield DataTable(id="results-table", zebra_stripes=True)

            yield Static("Not connected", id="status-bar")

        yield ContextFooter()

    def on_mount(self) -> None:
        """Initialize the app."""
        self._restart_argv = self._compute_restart_argv()

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

        if self._mock_profile:
            self.connections = self._mock_profile.connections.copy()
        else:
            self.connections = load_connections()

        self.refresh_tree()
        self._update_footer_bindings()

        self.object_tree.focus()
        # Move cursor to first node if available
        if self.object_tree.root.children:
            self.object_tree.cursor_line = 0
        self._update_section_labels()
        self._maybe_restore_connection_screen()
        if self._debug_mode:
            self.call_after_refresh(self._record_launch_ms)

    def _get_restart_cache_path(self) -> Path:
        return Path(tempfile.gettempdir()) / "sqlit-driver-install-restore.json"

    @staticmethod
    def _parse_startup_mark(value: str | None) -> float | None:
        if not value:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _record_launch_ms(self) -> None:
        base = self._startup_mark if self._startup_mark is not None else self._startup_init_time
        self._launch_ms = (time.perf_counter() - base) * 1000
        self._update_status_bar()

    def _maybe_restore_connection_screen(self) -> None:
        """Restore an in-progress connection form after a driver-install restart."""
        cache_path = self._get_restart_cache_path()
        if not cache_path.exists():
            return

        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            try:
                cache_path.unlink(missing_ok=True)
            except Exception:
                pass
            return

        try:
            cache_path.unlink(missing_ok=True)
        except Exception:
            pass

        if not isinstance(payload, dict) or payload.get("version") != 1:
            return

        values = payload.get("values")
        if not isinstance(values, dict):
            return

        editing = bool(payload.get("editing"))
        original_name = payload.get("original_name")
        post_install_message = payload.get("post_install_message")
        active_tab = payload.get("active_tab")

        config = None
        if editing and isinstance(original_name, str) and original_name:
            config = next((c for c in self.connections if getattr(c, "name", None) == original_name), None)

        if config is None:
            from .config import ConnectionConfig

            config = ConnectionConfig(
                name=str(values.get("name", "")),
                db_type=str(values.get("db_type", "mssql") or "mssql"),
            )
            editing = False

        prefill_values = {
            "values": values,
            "active_tab": active_tab,
        }

        from .ui.screens import ConnectionScreen

        self._set_connection_screen_footer()
        self.push_screen(
            ConnectionScreen(
                config,
                editing=editing,
                prefill_values=prefill_values,
                post_install_message=post_install_message if isinstance(post_install_message, str) else None,
            ),
            self._wrap_connection_result,
        )

    def watch_theme(self, old_theme: str, new_theme: str) -> None:
        """Save theme whenever it changes."""
        settings = load_settings()
        settings["theme"] = new_theme
        save_settings(settings)
