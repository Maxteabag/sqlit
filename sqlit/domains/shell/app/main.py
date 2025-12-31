"""Main Textual application for sqlit."""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.events import Key
from textual.lazy import Lazy
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import Static, Tree
from textual.worker import Worker

from sqlit.core.input_context import InputContext
from sqlit.core.key_router import resolve_action
from sqlit.core.vim import VimMode
from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.providers.model import DatabaseProvider
from sqlit.domains.connections.ui.mixins.connection import ConnectionMixin
from sqlit.domains.explorer.ui.mixins.tree import TreeMixin
from sqlit.domains.explorer.ui.mixins.tree_filter import TreeFilterMixin
from sqlit.domains.query.ui.mixins.autocomplete import AutocompleteMixin
from sqlit.domains.query.ui.mixins.query import QueryMixin
from sqlit.domains.results.ui.mixins.results import ResultsMixin
from sqlit.domains.results.ui.mixins.results_filter import ResultsFilterMixin
from sqlit.domains.shell.app.idle_scheduler import IdleScheduler
from sqlit.domains.shell.app.omarchy import DEFAULT_THEME
from sqlit.domains.shell.app.startup_flow import run_on_mount
from sqlit.domains.shell.app.theme_manager import ThemeManager
from sqlit.domains.shell.state import UIStateMachine
from sqlit.domains.shell.ui.mixins.ui_navigation import UINavigationMixin
from sqlit.shared.app import AppServices, RuntimeConfig, build_app_services
from sqlit.shared.ui.protocols import AppProtocol, UINavigationMixinHost
from sqlit.shared.ui.widgets import (
    AutocompleteDropdown,
    ContextFooter,
    InlineValueView,
    QueryTextArea,
    ResultsFilterInput,
    SqlitDataTable,
    TreeFilterInput,
)

if TYPE_CHECKING:
    from sqlit.domains.connections.app.session import ConnectionSession


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
    CSS_PATH = "main.css"

    LAYERS = ["autocomplete"]

    BINDINGS: ClassVar[list[Any]] = []

    def __init__(
        self,
        *,
        services: AppServices | None = None,
        runtime: RuntimeConfig | None = None,
        startup_connection: ConnectionConfig | None = None,
    ):
        super().__init__()
        self.services = services or build_app_services(runtime or RuntimeConfig.from_env())
        from sqlit.core.connection_manager import ConnectionManager

        self._connection_manager = ConnectionManager(self.services)
        self._startup_connection = startup_connection
        self._startup_connect_config: ConnectionConfig | None = None
        self._debug_mode = self.services.runtime.debug_mode
        self._debug_idle_scheduler = self.services.runtime.debug_idle_scheduler
        self._startup_profile = self.services.runtime.profile_startup
        self._startup_mark = self.services.runtime.startup_mark
        self._startup_init_time = time.perf_counter()
        self._startup_events: list[tuple[str, float]] = []
        self._launch_ms: float | None = None
        self._startup_stamp("init_start")
        self.connections: list[ConnectionConfig] = []
        self.current_connection: Any | None = None
        self.current_config: ConnectionConfig | None = None
        self.current_provider: DatabaseProvider | None = None
        self.current_ssh_tunnel: Any | None = None
        self.vim_mode: VimMode = VimMode.NORMAL
        self._expanded_paths: set[str] = set()
        self._leader_pending_menu: str = "leader"
        self._loading_nodes: set[str] = set()
        self._session: ConnectionSession | None = None
        self._schema_cache: dict[str, Any] = {
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
        self._value_view_active: bool = False
        self._last_result_columns: list[str] = []
        self._last_result_rows: list[tuple[Any, ...]] = []
        self._last_result_row_count: int = 0
        self._results_table_counter: int = 0
        self._internal_clipboard: str = ""
        # Undo/redo history for query editor
        self._undo_history: Any = None  # Lazy init UndoHistory
        self._fullscreen_mode: str = "none"
        self._last_notification: str = ""
        self._last_notification_severity: str = "information"
        self._last_notification_time: str = ""
        self._notification_timer: Timer | None = None
        self._notification_history: list[tuple[str, str, str]] = []
        self._connection_failed: bool = False
        self._leader_timer: Timer | None = None
        self._leader_pending: bool = False
        self._dialog_open: bool = False
        self._last_active_pane: str | None = None
        self._query_worker: Worker[Any] | None = None
        self._query_executing: bool = False
        self._query_handle: Any | None = None
        self._theme_manager = ThemeManager(self, settings_store=self.services.settings_store)
        self._spinner_index: int = 0
        self._spinner_timer: Timer | None = None
        # Schema indexing state
        self._schema_indexing: bool = False
        self._schema_worker: Worker[Any] | None = None
        self._schema_spinner_index: int = 0
        self._schema_spinner_timer: Timer | None = None
        self._table_metadata: dict[str, tuple[str, str, str | None]] = {}
        self._columns_loading: set[str] = set()
        self._state_machine = UIStateMachine()
        self._last_query_table: dict[str, Any] | None = None
        self._query_target_database: str | None = None  # Target DB for auto-generated queries
        # Idle scheduler for background work
        self._idle_scheduler: IdleScheduler | None = None
        self._startup_stamp("init_end")

    def _get_focus_pane(self) -> str:
        """Infer which pane currently has focus."""
        focused = getattr(self, "focused", None)
        widget = focused
        while widget:
            widget_id = getattr(widget, "id", None)
            if widget_id in ("object-tree", "sidebar"):
                return "explorer"
            if widget_id in ("query-input", "query-area"):
                return "query"
            if widget_id in ("results-table", "results-area", "value-view"):
                return "results"
            widget = getattr(widget, "parent", None)
        return "none"

    def _get_input_context(self) -> InputContext:
        """Build a UI-agnostic input context snapshot."""
        tree_node_kind = None
        tree_node_connection_name = None
        try:
            node = self.object_tree.cursor_node
            if node is not None:
                kind = ""
                if hasattr(self, "_get_node_kind"):
                    kind = getattr(self, "_get_node_kind")(node)
                tree_node_kind = kind or None
                if tree_node_kind == "connection":
                    data = getattr(node, "data", None)
                    config = getattr(data, "config", None)
                    if config is not None:
                        tree_node_connection_name = config.name
        except Exception:
            pass

        last_result_is_error = self._last_result_columns == ["Error"]
        current_connection_name = self.current_config.name if self.current_config else None

        return InputContext(
            focus=self._get_focus_pane(),
            vim_mode=self.vim_mode,
            leader_pending=self._leader_pending,
            leader_menu=self._leader_pending_menu,
            tree_filter_active=getattr(self, "_tree_filter_visible", False),
            autocomplete_visible=self._autocomplete_visible,
            results_filter_active=getattr(self, "_results_filter_visible", False),
            value_view_active=self._value_view_active,
            query_executing=self._query_executing,
            modal_open=self._dialog_open,
            has_connection=self.current_connection is not None,
            current_connection_name=current_connection_name,
            tree_node_kind=tree_node_kind,
            tree_node_connection_name=tree_node_connection_name,
            last_result_is_error=last_result_is_error,
        )

    def on_key(self, event: Key) -> None:
        """Route key presses through the core key router."""
        ctx = self._get_input_context()
        if ctx.modal_open:
            return

        action = resolve_action(
            event.key,
            ctx,
            is_allowed=lambda name: self._state_machine.check_action(ctx, name),
        )

        if action is None and ctx.leader_pending and hasattr(self, "_cancel_leader_pending"):
            cast(UINavigationMixinHost, self)._cancel_leader_pending()
            ctx = self._get_input_context()
            action = resolve_action(
                event.key,
                ctx,
                is_allowed=lambda name: self._state_machine.check_action(ctx, name),
            )

        if action:
            handler = getattr(self, f"action_{action}", None)
            if handler:
                handler()
                event.prevent_default()
                event.stop()


    @property
    def object_tree(self) -> Tree:
        return self.query_one("#object-tree", Tree)

    @property
    def query_input(self) -> QueryTextArea:
        return self.query_one("#query-input", QueryTextArea)

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
    def idle_scheduler_bar(self) -> Static:
        return self.query_one("#idle-scheduler-bar", Static)

    @property
    def autocomplete_dropdown(self) -> Any:
        from sqlit.shared.ui.widgets import AutocompleteDropdown

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
        app = cast(AppProtocol, self)
        if wait_for_dismiss:
            future = super().push_screen(screen, callback, wait_for_dismiss=True)
            app._update_footer_bindings()
            self._update_dialog_state()
            return future
        mount = super().push_screen(screen, callback, wait_for_dismiss=False)
        app._update_footer_bindings()
        self._update_dialog_state()
        return mount

    def pop_screen(self) -> Any:
        """Override pop_screen to update footer when screen changes."""
        result = super().pop_screen()
        app = cast(AppProtocol, self)
        app._update_footer_bindings()
        self._update_dialog_state()
        return result

    def _update_dialog_state(self) -> None:
        """Track whether a modal dialog is open and update pane title styling."""
        self._dialog_open = any(isinstance(screen, ModalScreen) for screen in self.screen_stack)
        app = cast(AppProtocol, self)
        app._update_section_labels()

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        """Check if an action is allowed in the current state.

        This method is pure - it only checks, never mutates state.
        State transitions happen in the action methods themselves.
        """
        return self._state_machine.check_action(self._get_input_context(), action)

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
                        yield QueryTextArea(
                            "",
                            language="sql",
                            id="query-input",
                            read_only=True,
                        )
                        yield Lazy(AutocompleteDropdown(id="autocomplete-dropdown"))

                    with Container(id="results-area"):
                        yield ResultsFilterInput(id="results-filter")
                        yield Lazy(SqlitDataTable(id="results-table", zebra_stripes=True, show_header=False))
                        yield InlineValueView(id="value-view")

            yield Static("", id="idle-scheduler-bar")
            yield Static("Not connected", id="status-bar")

        yield ContextFooter()
        self._startup_stamp("compose_end")

    def on_mount(self) -> None:
        """Initialize the app."""
        run_on_mount(cast(AppProtocol, self))

    def on_unmount(self) -> None:
        """Clean up background timers when the app exits."""
        if self._idle_scheduler is not None:
            self._idle_scheduler.stop()
            self._idle_scheduler = None
        if self._leader_timer is not None:
            self._leader_timer.stop()
            self._leader_timer = None
        idle_timer = getattr(self, "_idle_scheduler_bar_timer", None)
        if idle_timer is not None:
            idle_timer.stop()
            self._idle_scheduler_bar_timer = None

    def _startup_stamp(self, name: str) -> None:
        if not self._startup_profile:
            return
        self._startup_events.append((name, time.perf_counter()))

    def _record_launch_ms(self) -> None:
        base = self._startup_mark if self._startup_mark is not None else self._startup_init_time
        self._launch_ms = (time.perf_counter() - base) * 1000
        app = cast(AppProtocol, self)
        app._update_status_bar()

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
