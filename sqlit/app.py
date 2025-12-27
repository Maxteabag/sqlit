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
from textual.lazy import Lazy
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import Static, TextArea, Tree
from textual.worker import Worker

from .config import (
    ConnectionConfig,
    load_connections,
)
from .db import DatabaseAdapter
from .mock_settings import apply_mock_environment, build_mock_profile_from_settings
from .mocks import MockProfile
from .theme_manager import ThemeManager
from .omarchy import DEFAULT_THEME
from .state_machine import (
    UIStateMachine,
    get_leader_bindings,
)
from .ui.mixins import (
    AutocompleteMixin,
    ConnectionMixin,
    QueryMixin,
    ResultsFilterMixin,
    ResultsMixin,
    TreeFilterMixin,
    TreeMixin,
    UINavigationMixin,
)
from .widgets import (
    AutocompleteDropdown,
    ContextFooter,
    ResultsFilterInput,
    SqlitDataTable,
    TreeFilterInput,
    VimMode,
)


class SSMSTUI(
    TreeMixin,
    TreeFilterMixin,
    ConnectionMixin,
    QueryMixin,
    AutocompleteMixin,
    ResultsMixin,
    ResultsFilterMixin,
    UINavigationMixin,
    App,
):
    """Main SSMS TUI application."""

    TITLE = "sqlit"

    CSS = """
    Screen {
        background: $surface;
    }

    TextArea {
        & > .text-area--cursor-line {
            background: transparent;
        }
        &:focus > .text-area--cursor-line {
            background: $surface-lighten-1;
        }
    }

    DataTable.flash-cell:focus > .datatable--cursor,
    DataTable.flash-row:focus > .datatable--cursor,
    DataTable.flash-all:focus > .datatable--cursor {
        background: $success 30%;
    }

    DataTable.flash-all {
        border: solid $success 30%;
    }

    .flash {
        background: $success 30%;
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
        border: round $border;
        padding: 1;
        margin: 0;
    }

    #object-tree {
        height: 1fr;
    }

    #main-panel {
        width: 1fr;
    }

    #query-area {
        height: 50%;
        border: round $border;
        padding: 1;
        margin: 0;
    }

    #query-input {
        height: 1fr;
        border: none;
    }

    #results-area {
        height: 50%;
        padding: 1;
        border: round $border;
        margin: 0;
    }

    #sidebar.active-pane,
    #query-area.active-pane,
    #results-area.active-pane {
        border: round $primary;
        border-title-color: $primary;
    }


    #results-area DataTable {
        height: 1fr;
    }

    /* FastDataTable header styling */
    DataTable > .datatable--header {
        background: $surface-lighten-1;
        color: $primary;
        text-style: bold;
    }

    DataTable:focus > .datatable--header {
        background: $primary 20%;
        color: $text;
    }

    /* FastDataTable already has zebra stripes with $primary 10% */

    #status-bar {
        height: 1;
        background: $surface-darken-1;
        padding: 0 1;
    }

    #sidebar,
    #query-area,
    #results-area {
        border-title-align: left;
        border-title-color: $border;
        border-title-background: $surface;
        border-title-style: bold;
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
        Binding("ctrl+enter", "execute_query_insert", "Execute", show=False),
        Binding("d", "clear_query", "Clear", show=False),
        Binding("n", "new_query", "New", show=False),
        Binding("h", "show_history", "History", show=False),
        Binding("z", "collapse_tree", "Collapse", show=False),
        Binding("j", "tree_cursor_down", "Down", show=False),
        Binding("k", "tree_cursor_up", "Up", show=False),
        Binding("u", "use_database", "Use as default", show=False),
        Binding("v", "view_cell", "View cell", show=False),
        Binding("u", "edit_cell", "Update cell", show=False),
        Binding("h", "results_cursor_left", "Left", show=False),
        Binding("j", "results_cursor_down", "Down", show=False),
        Binding("k", "results_cursor_up", "Up", show=False),
        Binding("l", "results_cursor_right", "Right", show=False),
        Binding("y", "copy_context", "Copy", show=False),
        Binding("Y", "copy_row", "Copy row", show=False),
        Binding("a", "copy_results", "Copy results", show=False),
        Binding("x", "clear_results", "Clear results", show=False),
        Binding("ctrl+z", "cancel_operation", "Cancel", show=False),
        Binding("ctrl+j", "autocomplete_next", "Next suggestion", show=False),
        Binding("ctrl+k", "autocomplete_prev", "Prev suggestion", show=False),
        Binding("slash", "tree_filter", "Filter", show=False),
        Binding("escape", "tree_filter_close", "Close filter", show=False),
        Binding("enter", "tree_filter_accept", "Select", show=False),
        Binding("n", "tree_filter_next", "Next match", show=False),
        Binding("N", "tree_filter_prev", "Prev match", show=False),
        # Results filter bindings
        Binding("slash", "results_filter", "Filter results", show=False),
        Binding("escape", "results_filter_close", "Close filter", show=False),
        Binding("enter", "results_filter_accept", "Select", show=False),
        Binding("n", "results_filter_next", "Next match", show=False),
        Binding("N", "results_filter_prev", "Prev match", show=False),
    ]

    def __init__(
        self,
        mock_profile: MockProfile | None = None,
        startup_connection: ConnectionConfig | None = None,
    ):
        super().__init__()
        self._mock_profile = mock_profile
        self._startup_connection = startup_connection
        self._startup_connect_config: ConnectionConfig | None = None
        self._debug_mode = os.environ.get("SQLIT_DEBUG") == "1"
        self._startup_profile = os.environ.get("SQLIT_PROFILE_STARTUP") == "1"
        self._startup_mark = self._parse_startup_mark(os.environ.get("SQLIT_STARTUP_MARK"))
        self._startup_init_time = time.perf_counter()
        self._startup_events: list[tuple[str, float]] = []
        self._launch_ms: float | None = None
        self._startup_stamp("init_start")
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
        self._results_table_counter: int = 0
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
        self._dialog_open: bool = False
        self._last_active_pane: str | None = None
        self._query_worker: Worker[Any] | None = None
        self._query_executing: bool = False
        self._cancellable_query: Any | None = None
        self._theme_manager = ThemeManager(self)
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
        self._last_query_table: dict | None = None
        # Omarchy theme sync state

        if mock_profile:
            self._session_factory = self._create_mock_session_factory(mock_profile)
        self._startup_stamp("init_end")

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
    def results_table(self) -> SqlitDataTable:
        # The results table ID changes when replaced (results-table, results-table-1, etc.)
        # Query for any DataTable within the results-area container
        return self.query_one("#results-area DataTable")  # type: ignore[return-value]

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

    @property
    def tree_filter_input(self) -> TreeFilterInput:
        return self.query_one("#tree-filter", TreeFilterInput)

    @property
    def results_filter_input(self) -> ResultsFilterInput:
        return self.query_one("#results-filter", ResultsFilterInput)

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
            self._update_dialog_state()
            return future
        mount = super().push_screen(screen, callback, wait_for_dismiss=False)
        self._update_footer_bindings()
        self._update_dialog_state()
        return mount

    def pop_screen(self) -> Any:
        """Override pop_screen to update footer when screen changes."""
        result = super().pop_screen()
        self._update_footer_bindings()
        self._update_dialog_state()
        return result

    def _update_dialog_state(self) -> None:
        """Track whether a modal dialog is open and update pane title styling."""
        self._dialog_open = any(isinstance(screen, ModalScreen) for screen in self.screen_stack)
        self._update_section_labels()

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
        self._startup_stamp("compose_start")
        with Vertical(id="main-container"):
            with Horizontal(id="content"):
                with Vertical(id="sidebar"):
                    yield TreeFilterInput(id="tree-filter")
                    tree: Tree[Any] = Tree("Servers", id="object-tree")
                    tree.show_root = False
                    tree.guide_depth = 2
                    yield tree

                with Vertical(id="main-panel"):
                    with Container(id="query-area"):
                        yield TextArea(
                            "",
                            language="sql",
                            id="query-input",
                            read_only=True,
                        )
                        yield Lazy(AutocompleteDropdown(id="autocomplete-dropdown"))

                    with Container(id="results-area"):
                        yield ResultsFilterInput(id="results-filter")
                        yield Lazy(SqlitDataTable(id="results-table", zebra_stripes=True, show_header=False))

            yield Static("Not connected", id="status-bar")

        yield ContextFooter()
        self._startup_stamp("compose_end")

    def on_mount(self) -> None:
        """Initialize the app."""
        self._startup_stamp("on_mount_start")
        self._restart_argv = self._compute_restart_argv()

        self._theme_manager.register_builtin_themes()
        self._theme_manager.register_textarea_themes()

        settings = self._theme_manager.initialize()
        self._startup_stamp("settings_loaded")

        self._expanded_paths = set(settings.get("expanded_nodes", []))
        self._startup_stamp("settings_applied")

        self._apply_mock_settings(settings)

        if self._mock_profile:
            self.connections = self._mock_profile.connections.copy()
        else:
            self.connections = load_connections(load_credentials=False)
        if self._startup_connection:
            self._setup_startup_connection(self._startup_connection)
        self._startup_stamp("connections_loaded")

        self.refresh_tree()
        self._startup_stamp("tree_refreshed")

        self.object_tree.focus()
        self._startup_stamp("tree_focused")
        # Move cursor to first node if available
        if self.object_tree.root.children:
            self.object_tree.cursor_line = 0
        self._update_section_labels()
        self._maybe_restore_connection_screen()
        self._startup_stamp("restore_checked")
        if self._debug_mode:
            self.call_after_refresh(self._record_launch_ms)
        self.call_after_refresh(self._update_status_bar)
        self._update_footer_bindings()
        self._startup_stamp("footer_updated")
        if self._startup_connect_config:
            self.call_after_refresh(lambda: self.connect_to_server(self._startup_connect_config))  # type: ignore[arg-type]
        self._log_startup_timing()

    def _apply_mock_settings(self, settings: dict) -> None:
        apply_mock_environment(settings)
        if self._mock_profile:
            return
        mock_profile = build_mock_profile_from_settings(settings)
        if mock_profile:
            self._mock_profile = mock_profile
            self._session_factory = self._create_mock_session_factory(mock_profile)

    def _setup_startup_connection(self, config: ConnectionConfig) -> None:
        """Set up a startup connection to auto-connect after mount."""
        if not config.name:
            config.name = "Temp Connection"
        self._startup_connect_config = config

    def _startup_stamp(self, name: str) -> None:
        if not self._startup_profile:
            return
        self._startup_events.append((name, time.perf_counter()))

    def _log_startup_timing(self) -> None:
        if not self._startup_profile:
            return
        now = time.perf_counter()
        if self._startup_mark is not None:
            since_start = (now - self._startup_mark) * 1000
        else:
            since_start = None
        init_to_mount = (now - self._startup_init_time) * 1000

        parts = []
        if since_start is not None:
            parts.append(f"start_to_mount_ms={since_start:.2f}")
        parts.append(f"init_to_mount_ms={init_to_mount:.2f}")
        print(f"[sqlit] startup {' '.join(parts)}", file=sys.stderr)
        self._log_startup_steps()

        def after_refresh() -> None:
            now_refresh = time.perf_counter()
            if self._startup_mark is not None:
                start_to_refresh = (now_refresh - self._startup_mark) * 1000
            else:
                start_to_refresh = None
            init_to_refresh = (now_refresh - self._startup_init_time) * 1000

            self._log_startup_step("first_refresh", now_refresh)
            refresh_parts = []
            if start_to_refresh is not None:
                refresh_parts.append(f"start_to_first_refresh_ms={start_to_refresh:.2f}")
            refresh_parts.append(f"init_to_first_refresh_ms={init_to_refresh:.2f}")
            print(f"[sqlit] startup {' '.join(refresh_parts)}", file=sys.stderr)

        self.call_after_refresh(after_refresh)

    def _log_startup_steps(self) -> None:
        for name, ts in self._startup_events:
            self._log_startup_step(name, ts)

    def _log_startup_step(self, name: str, timestamp: float) -> None:
        if not self._startup_profile:
            return
        parts = [f"step={name}"]
        if self._startup_mark is not None:
            parts.append(f"start_ms={(timestamp - self._startup_mark) * 1000:.2f}")
        parts.append(f"init_ms={(timestamp - self._startup_init_time) * 1000:.2f}")
        print(f"[sqlit] startup {' '.join(parts)}", file=sys.stderr)

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
        self._theme_manager.on_theme_changed(new_theme)

    def get_custom_theme_names(self) -> set[str]:
        return self._theme_manager.get_custom_theme_names()

    def add_custom_theme(self, theme_name: str) -> str:
        return self._theme_manager.add_custom_theme(theme_name)

    def open_custom_theme_in_editor(self, theme_name: str) -> None:
        self._theme_manager.open_custom_theme_in_editor(theme_name)

    def get_custom_theme_path(self, theme_name: str) -> Path:
        return self._theme_manager.get_custom_theme_path(theme_name)

    def _apply_theme_safe(self, theme_name: str) -> None:
        """Apply a theme with fallback to default on error."""
        try:
            self.theme = theme_name
        except Exception:
            try:
                self.theme = DEFAULT_THEME
            except Exception:
                self.theme = "sqlit"
