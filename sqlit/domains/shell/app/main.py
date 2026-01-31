"""Main Textual application for sqlit."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
from datetime import datetime
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.events import Key
from textual.lazy import Lazy
from textual.reactive import reactive
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
from sqlit.domains.shell.app.commands import dispatch_command
from sqlit.domains.shell.app.idle_scheduler import IdleScheduler
from sqlit.domains.shell.app.omarchy import DEFAULT_THEME
from sqlit.domains.shell.app.startup_flow import run_on_mount
from sqlit.domains.shell.app.theme_manager import ThemeManager
from sqlit.domains.shell.state import UIStateMachine
from sqlit.domains.shell.ui.mixins.ui_navigation import UINavigationMixin
from sqlit.shared.app import AppServices, RuntimeConfig, build_app_services
from sqlit.shared.core.debug_events import (
    DebugEvent,
    DebugEventBus,
    format_debug_data,
    serialize_debug_event,
    set_debug_emitter,
)
from sqlit.shared.core.store import CONFIG_DIR
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
from sqlit.shared.ui.widgets_stacked_results import StackedResultsContainer

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

    query_executing: bool = reactive(False)
    current_connection: Any | None = reactive(None)
    current_config: ConnectionConfig | None = reactive(None)
    current_provider: DatabaseProvider | None = reactive(None)
    current_ssh_tunnel: Any | None = reactive(None)

    def __init__(
        self,
        *,
        services: AppServices | None = None,
        runtime: RuntimeConfig | None = None,
        startup_connection: ConnectionConfig | None = None,
        exclusive_connection: bool = False,
    ):
        super().__init__()
        self.services = services or build_app_services(runtime or RuntimeConfig.from_env())
        from sqlit.core.connection_manager import ConnectionManager

        self._connection_manager = ConnectionManager(self.services)
        self._startup_connection = startup_connection
        self._exclusive_connection = exclusive_connection
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
        self._selected_connection_names: set[str] = set()
        self._tree_visual_mode_anchor: str | None = None
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
        self._suppress_autocomplete_once: bool = False
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
        self._query_handle: Any | None = None
        self._command_mode: bool = False
        self._command_buffer: str = ""
        self._count_buffer: str = ""  # Vim count prefix (e.g., "3" for 3j)
        self._ui_stall_watchdog_timer: Timer | None = None
        self._ui_stall_watchdog_expected: float | None = None
        self._ui_stall_watchdog_interval_s: float = 0.0
        self._ui_stall_watchdog_threshold_s: float = 0.0
        self._ui_stall_watchdog_events: list[tuple[str, float, str]] = []
        self._ui_stall_watchdog_log_path: Path = CONFIG_DIR / "ui_stall_watchdog.txt"
        self._debug_event_bus = DebugEventBus()
        self._debug_events_enabled: bool = False
        self._debug_event_history: list[DebugEvent] = []
        self._debug_event_history_limit: int = 200
        self._debug_event_recent_window_s: float = 2.0
        self._debug_event_recent_limit: int = 40
        self._debug_event_log_path: Path = CONFIG_DIR / "debug_events.txt"
        set_debug_emitter(self.emit_debug_event)
        self._last_key: str | None = None
        self._last_key_char: str | None = None
        self._last_key_at: float | None = None
        self._last_action: str | None = None
        self._last_action_at: float | None = None
        self._last_command: str | None = None
        self._last_command_at: float | None = None
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
        self._restart_requested: bool = False
        # Idle scheduler for background work
        self._idle_scheduler: IdleScheduler | None = None
        self._startup_stamp("init_end")

    @property
    def current_adapter(self) -> Any | None:
        """Compatibility alias for the active adapter."""
        if self.current_provider is None:
            return None
        return self.current_provider.connection_factory

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
        tree_node_connection_selected = False
        try:
            node = self.object_tree.cursor_node
            if node is not None:
                kind = ""
                if hasattr(self, "_get_node_kind"):
                    kind = self._get_node_kind(node)
                tree_node_kind = kind or None
                if tree_node_kind == "connection":
                    data = getattr(node, "data", None)
                    config = getattr(data, "config", None)
                    if config is not None:
                        tree_node_connection_name = config.name
                        selected = getattr(self, "_selected_connection_names", set())
                        tree_node_connection_selected = config.name in selected
        except Exception:
            pass

        last_result_is_error = self._last_result_columns == ["Error"]
        current_connection_name = self.current_config.name if self.current_config else None
        has_results = bool(self._last_result_columns) and bool(self._last_result_rows)
        stacked_result_count = 0
        if hasattr(self, "results_area"):
            try:
                if self.results_area.has_class("stacked-mode"):
                    from sqlit.shared.ui.widgets_stacked_results import StackedResultsContainer

                    container = self.query_one("#stacked-results", StackedResultsContainer)
                    stacked_result_count = container.section_count
                    if not has_results:
                        has_results = stacked_result_count > 0
            except Exception:
                pass

        # Compute modal_open dynamically from screen stack for accurate state
        modal_open = any(isinstance(screen, ModalScreen) for screen in self.screen_stack)

        # Get value view state for tree/syntax mode
        value_view_tree_mode = False
        value_view_is_json = False
        if self._value_view_active:
            try:
                from sqlit.shared.ui.widgets import InlineValueView

                value_view = self.query_one("#value-view", InlineValueView)
                value_view_tree_mode = value_view._tree_mode
                value_view_is_json = value_view._is_json
            except Exception:
                pass

        return InputContext(
            focus=self._get_focus_pane(),
            vim_mode=self.vim_mode,
            leader_pending=self._leader_pending,
            leader_menu=self._leader_pending_menu,
            tree_filter_active=getattr(self, "_tree_filter_visible", False),
            tree_multi_select_active=bool(getattr(self, "_selected_connection_names", set())),
            tree_visual_mode_active=getattr(self, "_tree_visual_mode_anchor", None) is not None,
            autocomplete_visible=self._autocomplete_visible,
            results_filter_active=getattr(self, "_results_filter_visible", False),
            value_view_active=self._value_view_active,
            value_view_tree_mode=value_view_tree_mode,
            value_view_is_json=value_view_is_json,
            query_executing=self.query_executing,
            modal_open=modal_open,
            has_connection=self.current_connection is not None,
            current_connection_name=current_connection_name,
            tree_node_kind=tree_node_kind,
            tree_node_connection_name=tree_node_connection_name,
            tree_node_connection_selected=tree_node_connection_selected,
            last_result_is_error=last_result_is_error,
            has_results=has_results,
            stacked_result_count=stacked_result_count,
            count_buffer=self._count_buffer,
        )

    def _debug_screen_label(self, screen: Any | None) -> str:
        if screen is None:
            return "none"
        name = getattr(screen, "name", None)
        if name:
            return str(name)
        return screen.__class__.__name__

    def _debug_screen_stack(self) -> list[str]:
        try:
            return [self._debug_screen_label(screen) for screen in self.screen_stack]
        except Exception:
            return []

    def emit_debug_event(self, name: str, *, category: str = "", **data: Any) -> None:
        self._debug_event_bus.emit(name, category=category, **data)

    def _handle_debug_event(self, event: DebugEvent) -> None:
        self._debug_event_history.append(event)
        if len(self._debug_event_history) > self._debug_event_history_limit:
            self._debug_event_history = self._debug_event_history[-self._debug_event_history_limit:]
        self._write_debug_event(event)

    def _collect_recent_debug_events(self, *, now: float) -> list[dict[str, Any]]:
        if not self._debug_events_enabled:
            return []
        events = self._debug_event_history
        if not events:
            return []
        cutoff = now - self._debug_event_recent_window_s
        recent = [event for event in events if event.ts >= cutoff]
        if not recent:
            return []
        if len(recent) > self._debug_event_recent_limit:
            recent = recent[-self._debug_event_recent_limit:]
        summaries: list[dict[str, Any]] = []
        for event in recent:
            summaries.append(
                {
                    "time": event.iso,
                    "name": event.name,
                    "category": event.category,
                    "data": format_debug_data(event.data, max_len=160),
                    "age_ms": int((now - event.ts) * 1000),
                }
            )
        return summaries

    def _write_debug_event(self, event: DebugEvent) -> None:
        path = self._debug_event_log_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                path.parent.chmod(0o700)
            except OSError:
                pass
            with path.open("a", encoding="utf-8") as handle:
                handle.write(serialize_debug_event(event))
                handle.write("\n")
        except Exception:
            pass

    def _set_debug_events_enabled(self, enabled: bool) -> None:
        if enabled == self._debug_events_enabled:
            return
        if enabled:
            self._debug_event_bus.subscribe(self._handle_debug_event)
        else:
            self._debug_event_bus.unsubscribe(self._handle_debug_event)
        self._debug_events_enabled = enabled
        if enabled:
            try:
                from sqlit.core.keymap import emit_keybinding_snapshot

                emit_keybinding_snapshot()
            except Exception:
                pass

    async def _check_bindings(self, key: str, priority: bool = False) -> bool:
        chain = (
            reversed(self.screen._binding_chain)
            if priority
            else self.screen._modal_binding_chain
        )
        for namespace, bindings in chain:
            key_bindings = bindings.key_to_bindings.get(key, ())
            for binding in key_bindings:
                if binding.priority != priority:
                    continue
                handled = await self.run_action(binding.action, namespace)
                if handled:
                    self.emit_debug_event(
                        "keybinding.execute",
                        category="keybinding",
                        source="textual",
                        key=key,
                        action=binding.action,
                        namespace=namespace.__class__.__name__,
                        namespace_id=getattr(namespace, "id", None),
                        screen=self._debug_screen_label(self.screen),
                        priority=priority,
                    )
                    return True
        return False

    def on_key(self, event: Key) -> None:
        """Route key presses through the core key router."""
        self._last_key = event.key
        self._last_key_char = event.character
        self._last_key_at = time.perf_counter()
        ctx = self._get_input_context()
        if ctx.modal_open:
            if event.key in {"escape", "enter"}:
                self.emit_debug_event(
                    "key.modal",
                    key=event.key,
                    screen=self._debug_screen_label(self.screen),
                    stack=self._debug_screen_stack(),
                )
            return

        if self._handle_command_input(event, ctx):
            return

        # Handle count digit accumulation (e.g., 3j, 10k)
        if self._handle_count_digit(event, ctx):
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
                self.emit_debug_event(
                    "keybinding.execute",
                    category="keybinding",
                    source="core",
                    key=event.key,
                    action=action,
                    screen=self._debug_screen_label(self.screen),
                    state=self._state_machine.get_active_state_name(ctx),
                    focus=ctx.focus,
                    vim_mode=str(ctx.vim_mode),
                    leader_pending=ctx.leader_pending,
                )
                self._last_action = action
                self._last_action_at = time.perf_counter()
                handler()
                event.prevent_default()
                event.stop()

    def push_screen(
        self,
        screen: Any,
        callback: Callable[[Any], None] | Callable[[Any], Awaitable[None]] | None = None,
        wait_for_dismiss: bool = False,
    ) -> Any:
        stack_before = self._debug_screen_stack()
        result = super().push_screen(screen, callback, wait_for_dismiss)
        screen_label = screen if isinstance(screen, str) else self._debug_screen_label(screen)
        self.emit_debug_event(
            "screen.push",
            screen=screen_label,
            stack_before=stack_before,
            stack_after=self._debug_screen_stack(),
        )
        return result

    def pop_screen(self) -> Any:
        stack_before = self._debug_screen_stack()
        result = super().pop_screen()
        self.emit_debug_event(
            "screen.pop",
            stack_before=stack_before,
            stack_after=self._debug_screen_stack(),
        )
        return result

    def _start_command_mode(self) -> None:
        if getattr(self, "_leader_pending", False) and hasattr(self, "_cancel_leader_pending"):
            cast(UINavigationMixinHost, self)._cancel_leader_pending()
        self._command_mode = True
        self._command_buffer = ""
        self._update_status_bar()

    def _exit_command_mode(self) -> None:
        self._command_mode = False
        self._command_buffer = ""
        self._update_status_bar()

    # ========================================================================
    # Vim count prefix support
    # ========================================================================

    def _get_and_clear_count(self) -> int | None:
        """Get the current count prefix and clear it. Returns None if no count."""
        if not self._count_buffer:
            return None
        try:
            count = int(self._count_buffer)
            # Cap at 9999 for safety
            count = min(count, 9999)
        except ValueError:
            count = None
        self._count_buffer = ""
        return count

    def _append_count_digit(self, digit: str) -> None:
        """Append a digit to the count buffer."""
        if len(self._count_buffer) < 4:  # Max 4 digits (9999)
            self._count_buffer += digit

    def _clear_count_buffer(self) -> None:
        """Clear the count buffer."""
        self._count_buffer = ""

    def _handle_count_digit(self, event: Key, ctx: InputContext) -> bool:
        """Handle digit keys for count prefix accumulation.

        Returns True if the digit was consumed as a count prefix.
        """
        from sqlit.core.vim import VimMode

        # Only in NORMAL mode with query focus
        if ctx.focus != "query" or self.vim_mode != VimMode.NORMAL:
            return False

        # Don't intercept digits during leader pending
        if ctx.leader_pending:
            return False

        char = event.character
        if not char or not char.isdigit():
            return False

        # '0' only appends if count already started (otherwise it's line-start motion)
        if char == "0" and not self._count_buffer:
            return False

        # Digits 1-9 always start/continue count
        self._append_count_digit(char)
        event.prevent_default()
        event.stop()
        return True

    def _handle_command_input(self, event: Key, ctx: InputContext) -> bool:
        from sqlit.core.vim import VimMode

        if not self._command_mode:
            is_command_start = event.character == ":" or event.key in {":", "colon", "shift+semicolon"}
            if not is_command_start:
                return False
            if ctx.focus == "query" and self.vim_mode == VimMode.INSERT:
                return False
            self._start_command_mode()
            event.prevent_default()
            event.stop()
            return True

        if event.key == "escape":
            self._exit_command_mode()
        elif event.key == "enter":
            command = self._command_buffer.strip()
            self._exit_command_mode()
            self._run_command(command)
        elif event.key in ("backspace", "delete"):
            if self._command_buffer:
                self._command_buffer = self._command_buffer[:-1]
                self._update_status_bar()
            else:
                self._exit_command_mode()
        else:
            char = event.character
            if char and len(char) == 1:
                self._command_buffer += char
                self._update_status_bar()
            else:
                event.prevent_default()
                event.stop()
                return True

        event.prevent_default()
        event.stop()
        return True

    def _run_command(self, command: str) -> None:
        if not command:
            return

        normalized = command.strip()
        self._last_command = normalized
        self._last_command_at = time.perf_counter()

        # Handle go-to-line command (e.g., :25 goes to line 25)
        if normalized.isdigit():
            self._goto_line(int(normalized))
            return

        cmd, *args = normalized.split()
        cmd = cmd.lower()

        if cmd in {"commands", "cmds"}:
            self._show_command_list()
            return

        if cmd in {"version", "ver"}:
            self._show_version_info()
            return

        if cmd in {"q", "quit", "exit"}:
            try:
                handler = getattr(self, "action_quit", None)
                if callable(handler):
                    handler()
                else:
                    self.exit()
            except Exception:
                self.exit()
            return

        command_actions = {
            "help": "show_help",
            "h": "show_help",
            "connect": "show_connection_picker",
            "c": "show_connection_picker",
            "disconnect": "disconnect",
            "dc": "disconnect",
            "theme": "change_theme",
            "run": "execute_query",
            "r": "execute_query",
            "run!": "execute_query_insert",
            "r!": "execute_query_insert",
            "process-worker": "toggle_process_worker",
            "process_worker": "toggle_process_worker",
            "process-worker!": "toggle_process_worker",
            "worker": "toggle_process_worker",
        }

        if cmd == "set" and args:
            target = args[0].lower().replace("-", "_")
            value = args[1].lower() if len(args) > 1 else ""
            # Line number settings (vim-style)
            if target in {"number", "nu"}:
                self._set_line_numbers(True)
                return
            if target in {"nonumber", "nonu"}:
                self._set_line_numbers(False)
                return
            if target in {"relativenumber", "rnu"}:
                self._set_relative_line_numbers(True)
                return
            if target in {"norelativenumber", "nornu"}:
                self._set_relative_line_numbers(False)
                return
            if target in {"process_worker"}:
                if not value:
                    self._execute_command_action("toggle_process_worker")
                    return
                enable_values = {"1", "true", "on", "yes", "enable", "enabled"}
                disable_values = {"0", "false", "off", "no", "disable", "disabled"}
                if value in enable_values:
                    self._set_process_worker(True)
                    return
                if value in disable_values:
                    self._set_process_worker(False)
                    return
                self.notify(f"Unknown value for process_worker: {value}", severity="warning")
                return
            if target in {"process_worker_warm", "process_worker_warm_on_idle", "process_worker_lazy"}:
                if not value:
                    current = bool(self.services.runtime.process_worker_warm_on_idle)
                    desired = not current
                else:
                    enable_values = {"1", "true", "on", "yes", "enable", "enabled"}
                    disable_values = {"0", "false", "off", "no", "disable", "disabled"}
                    if value in enable_values:
                        desired = True
                    elif value in disable_values:
                        desired = False
                    else:
                        self.notify(f"Unknown value for {target}: {value}", severity="warning")
                        return
                if target == "process_worker_lazy":
                    desired = not desired
                self._set_process_worker_warm_on_idle(desired)
                return
            if target in {"process_worker_auto_shutdown", "process_worker_auto_shutdown_s"}:
                if not value:
                    self.notify("Provide seconds or 'off' for process_worker_auto_shutdown", severity="warning")
                    return
                disable_values = {"0", "false", "off", "no", "disable", "disabled"}
                if value in disable_values:
                    self._set_process_worker_auto_shutdown(0.0)
                    return
                try:
                    seconds = float(value)
                except ValueError:
                    self.notify(f"Invalid process_worker_auto_shutdown value: {value}", severity="warning")
                    return
                if seconds < 0:
                    self.notify("process_worker_auto_shutdown must be >= 0", severity="warning")
                    return
                self._set_process_worker_auto_shutdown(seconds)
                return

        if dispatch_command(self, cmd, args):
            return

        action = command_actions.get(cmd)
        if action is None:
            self.notify("Unknown command. Try :commands", severity="warning")
            return
        self._execute_command_action(action)

    def _show_command_list(self) -> None:
        columns = ["Title", "Command", "Description", "Hint"]
        rows = [
            ("General", ":commands", "Show this command list", ""),
            ("General", ":version, :ver", "Show version and git hash", ""),
            ("General", ":help, :h", "Show keyboard shortcuts", ""),
            ("General", ":q, :quit, :exit", "Quit sqlit", ""),
            ("Connection", ":connect, :c", "Open connection picker", ""),
            ("Connection", ":disconnect, :dc", "Disconnect from current server", ""),
            (
                "Connection",
                ":credentials [plaintext|keyring]",
                "Configure password storage",
                "Use 'plaintext' to store passwords in ~/.sqlit/ (protected folder), 'keyring' to use system keyring.",
            ),
            ("Appearance", ":theme", "Open theme selection", ""),
            ("Query", ":alert off|delete|write", "Confirm before risky queries", "Modes: off, delete, write"),
            ("Query", ":run, :r", "Execute query", ""),
            ("Query", ":run!, :r!", "Execute query (stay in INSERT)", ""),
            (
                "Navigation",
                ":<number>",
                "Go to line number",
                "Jump to specified line in query editor (e.g., :25 goes to line 25).",
            ),
            (
                "Navigation",
                "<count>G",
                "Go to line with count prefix",
                "In NORMAL mode, type a number then G to go to that line (e.g., 25G).",
            ),
            ("Editor", ":set number, :set nu", "Show line numbers", ""),
            ("Editor", ":set nonumber, :set nonu", "Hide line numbers", ""),
            ("Editor", ":set relativenumber, :set rnu", "Show relative line numbers", ""),
            ("Editor", ":set norelativenumber, :set nornu", "Show absolute line numbers", ""),
            (
                "Worker",
                ":process-worker, :worker",
                "Toggle process worker",
                "Spawns a separate OS process to run SQL queries, avoiding GIL starvation for better UI responsiveness; uses more RAM while active.",
            ),
            (
                "Worker",
                ":worker info",
                "Show process worker status",
                "Displays worker mode, active state, and last activity.",
            ),
            ("Settings", ":set process_worker_warm on|off", "Warm worker on idle", ""),
            ("Settings", ":set process_worker_lazy on|off", "Lazy worker start", ""),
            ("Settings", ":set process_worker_auto_shutdown <seconds>", "Auto-shutdown worker", ""),
            (
                "Watchdog",
                ":wd <ms|off>",
                "Set UI stall watchdog threshold",
                "Logs when the UI thread stalls longer than the threshold.",
            ),
            ("Watchdog", ":wd list", "Show UI stall warnings", ""),
            ("Watchdog", ":wd clear", "Clear UI stall log", ""),
            (
                "Debug",
                ":debug on|off",
                "Toggle debug event logging",
                "Captures screen stack, connection picker, password prompts, and key events.",
            ),
            ("Debug", ":debug", "Show debug status", ""),
            ("Debug", ":debug list", "Show debug events", ""),
            ("Debug", ":debug clear", "Clear debug event log", ""),
        ]
        if hasattr(self, "_replace_results_table"):
            self._replace_results_table(columns, rows)

    def _resolve_repo_root(self) -> Path | None:
        path = Path(__file__).resolve()
        for parent in (path, *path.parents):
            if (parent / ".git").exists():
                return parent
        return None

    def _parse_git_hash_from_version(self, version: str) -> str | None:
        import re

        match = re.search(r"\\+g([0-9a-fA-F]{7,})", version)
        if not match:
            return None
        return match.group(1)

    def _get_git_info(self) -> tuple[str | None, bool | None]:
        repo_root = self._resolve_repo_root()
        if repo_root is None:
            return None, None
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=repo_root,
                check=False,
                capture_output=True,
                text=True,
            )
            git_hash = result.stdout.strip() or None
        except Exception:
            git_hash = None
        dirty: bool | None = None
        try:
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_root,
                check=False,
                capture_output=True,
                text=True,
            )
            if status.stdout is not None:
                dirty = bool(status.stdout.strip())
        except Exception:
            dirty = None
        return git_hash, dirty

    def _show_version_info(self) -> None:
        try:
            from sqlit import __version__ as pkg_version
        except Exception:
            pkg_version = "unknown"

        git_hash = self._parse_git_hash_from_version(pkg_version)
        dirty: bool | None = None
        if git_hash is None:
            git_hash, dirty = self._get_git_info()
        else:
            _repo_hash, dirty = self._get_git_info()

        git_display = git_hash or "unknown"
        dirty_display = "unknown"
        if dirty is True:
            dirty_display = "yes"
            if git_hash:
                git_display = f"{git_display} (dirty)"
        elif dirty is False:
            dirty_display = "no"

        info_rows = [
            ("version", pkg_version),
            ("git", git_display),
            ("dirty", dirty_display),
            ("python", platform.python_version()),
            ("platform", sys.platform),
        ]

        if hasattr(self, "_replace_results_table"):
            self._replace_results_table(["Key", "Value"], info_rows)

        summary = f"sqlit {pkg_version}"
        if git_hash:
            summary = f"{summary} ({git_hash})"
        self.notify(summary, severity="information")

    def _execute_command_action(self, action: str) -> None:
        ctx = self._get_input_context()
        if not self._state_machine.check_action(ctx, action):
            self.notify(f"Command not available: {action}", severity="warning")
            return
        handler = getattr(self, f"action_{action}", None)
        if not callable(handler):
            self.notify(f"Unknown action: {action}", severity="warning")
            return
        handler()

    def _set_process_worker(self, enabled: bool) -> None:
        self.services.runtime.process_worker = enabled
        try:
            self.services.settings_store.set("process_worker", enabled)
        except Exception:
            pass
        if not enabled:
            close_fn = getattr(self, "_close_process_worker_client", None)
            if callable(close_fn):
                close_fn()
            cancel_warm = getattr(self, "_cancel_process_worker_warm", None)
            if callable(cancel_warm):
                cancel_warm()
        else:
            schedule_warm = getattr(self, "_schedule_process_worker_warm", None)
            if callable(schedule_warm):
                schedule_warm()
        state = "enabled" if enabled else "disabled"
        self.notify(f"Process worker {state}")

    def _goto_line(self, line_number: int) -> None:
        """Go to a specific line number (1-indexed)."""
        try:
            lines = self.query_input.text.split("\n")
            num_lines = len(lines)
            # Convert to 0-indexed and clamp
            target_row = min(line_number - 1, num_lines - 1)
            target_row = max(0, target_row)
            self.query_input.cursor_location = (target_row, 0)
            self.query_input.focus()
        except Exception:
            pass

    def _set_line_numbers(self, enabled: bool) -> None:
        """Enable or disable line numbers in the query editor."""
        try:
            self.query_input.show_line_numbers = enabled
        except Exception:
            pass
        try:
            self.services.settings_store.set("show_line_numbers", enabled)
        except Exception:
            pass
        state = "enabled" if enabled else "disabled"
        self.notify(f"Line numbers {state}")

    def _set_relative_line_numbers(self, enabled: bool) -> None:
        """Enable or disable relative line numbers in the query editor."""
        try:
            self.query_input.relative_line_numbers = enabled
            # Also ensure line numbers are visible when enabling relative
            if enabled and not self.query_input.show_line_numbers:
                self.query_input.show_line_numbers = True
        except Exception:
            pass
        try:
            self.services.settings_store.set("relative_line_numbers", enabled)
        except Exception:
            pass
        state = "enabled" if enabled else "disabled"
        self.notify(f"Relative line numbers {state}")

    def _set_process_worker_warm_on_idle(self, enabled: bool) -> None:
        self.services.runtime.process_worker_warm_on_idle = enabled
        try:
            self.services.settings_store.set("process_worker_warm_on_idle", enabled)
        except Exception:
            pass
        cancel_warm = getattr(self, "_cancel_process_worker_warm", None)
        if callable(cancel_warm):
            cancel_warm()
        if enabled and self.services.runtime.process_worker:
            schedule_warm = getattr(self, "_schedule_process_worker_warm", None)
            if callable(schedule_warm):
                schedule_warm()
        state = "enabled" if enabled else "disabled"
        self.notify(f"Process worker warm-on-idle {state}")

    def _set_process_worker_auto_shutdown(self, seconds: float) -> None:
        self.services.runtime.process_worker_auto_shutdown_s = float(seconds)
        try:
            self.services.settings_store.set("process_worker_auto_shutdown_s", float(seconds))
        except Exception:
            pass
        if seconds <= 0:
            clear_fn = getattr(self, "_clear_process_worker_auto_shutdown", None)
            if callable(clear_fn):
                clear_fn()
            state = "disabled"
        else:
            arm_fn = getattr(self, "_arm_process_worker_auto_shutdown", None)
            if callable(arm_fn):
                arm_fn()
            state = f"{seconds:g}s"
        self.notify(f"Process worker auto-shutdown {state}")


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
        """Request a clean restart after the app exits."""
        if getattr(self, "_restart_argv", None) is None:
            self._restart_argv = self._compute_restart_argv()
        self._restart_requested = True
        self.exit()

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
                            theme="css",
                            id="query-input",
                            read_only=True,
                        )
                        yield Lazy(AutocompleteDropdown(id="autocomplete-dropdown"))

                    with Container(id="results-area"):
                        yield ResultsFilterInput(id="results-filter")
                        yield Lazy(SqlitDataTable(id="results-table", zebra_stripes=True, show_header=False))
                        yield StackedResultsContainer(id="stacked-results")
                        yield InlineValueView(id="value-view")

            yield Static("", id="idle-scheduler-bar")
            yield Static("Not connected", id="status-bar")

        yield ContextFooter()
        self._startup_stamp("compose_end")

    def on_mount(self) -> None:
        """Initialize the app."""
        run_on_mount(cast(AppProtocol, self))
        self._apply_theme_classes()

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
        if self._ui_stall_watchdog_timer is not None:
            self._ui_stall_watchdog_timer.stop()
            self._ui_stall_watchdog_timer = None

    def _startup_stamp(self, name: str) -> None:
        if not self._startup_profile:
            return
        self._startup_events.append((name, time.perf_counter()))

    def _record_launch_ms(self) -> None:
        base = self._startup_mark if self._startup_mark is not None else self._startup_init_time
        self._launch_ms = (time.perf_counter() - base) * 1000
        app = cast(AppProtocol, self)
        app._update_status_bar()

    def get_theme_variable_defaults(self) -> dict[str, str]:
        from sqlit.domains.shell.app.themes import DEFAULT_MODE_COLORS

        theme_key = "dark" if self.current_theme.dark else "light"
        return dict(DEFAULT_MODE_COLORS[theme_key])

    def watch_theme(self, old_theme: str, new_theme: str) -> None:
        """Save theme whenever it changes."""
        self._apply_theme_classes()
        self._theme_manager.on_theme_changed(new_theme)
        self._update_footer_bindings()
        self._update_status_bar()
        try:
            self.query_input.sync_terminal_cursor()
        except Exception:
            pass

    def _apply_theme_classes(self) -> None:
        is_ansi = self.theme == "textual-ansi"
        self.set_class(is_ansi, "theme-ansi")
        for screen in self.screen_stack:
            try:
                screen.set_class(is_ansi, "theme-ansi")
            except Exception:
                pass

    def watch_query_executing(self, old_value: bool, new_value: bool) -> None:
        """React to query execution status changes."""
        self._update_footer_bindings()
        self._update_status_bar()

    def _start_ui_stall_watchdog(self) -> None:
        threshold_ms = float(getattr(self.services.runtime, "ui_stall_watchdog_ms", 0) or 0)
        if threshold_ms <= 0:
            return
        interval = min(0.2, max(0.05, (threshold_ms / 1000.0) / 2.0))
        self._ui_stall_watchdog_threshold_s = threshold_ms / 1000.0
        self._ui_stall_watchdog_interval_s = interval
        self._ui_stall_watchdog_expected = time.perf_counter() + interval
        if self._ui_stall_watchdog_timer is not None:
            self._ui_stall_watchdog_timer.stop()
        self._ui_stall_watchdog_timer = self.set_interval(interval, self._check_ui_stall)

    def _check_ui_stall(self) -> None:
        if self._ui_stall_watchdog_expected is None:
            self._ui_stall_watchdog_expected = time.perf_counter() + self._ui_stall_watchdog_interval_s
            return
        now = time.perf_counter()
        expected = self._ui_stall_watchdog_expected
        stall = now - expected
        if stall > self._ui_stall_watchdog_threshold_s:
            suffix = self._build_ui_stall_context()
            wall_now = time.time()
            recent_debug = self._collect_recent_debug_events(now=wall_now)
            try:
                timestamp = datetime.now().strftime("%H:%M:%S")
            except Exception:
                timestamp = ""
            self._ui_stall_watchdog_events.append((timestamp, stall * 1000.0, suffix))
            if len(self._ui_stall_watchdog_events) > 50:
                self._ui_stall_watchdog_events = self._ui_stall_watchdog_events[-50:]
            extra_lines: list[str] = []
            if recent_debug:
                context = suffix.strip()
                if context.startswith("(") and context.endswith(")"):
                    context = context[1:-1]
                self.emit_debug_event(
                    "watchdog.stall",
                    category="watchdog",
                    stall_ms=stall * 1000.0,
                    context=context,
                    recent=recent_debug,
                )
                for item in recent_debug:
                    data = item.get("data", "")
                    data_suffix = f" {data}" if data else ""
                    extra_lines.append(
                        f"  debug {item.get('time','')} {item.get('category','')} {item.get('name','')} age={item.get('age_ms',0)}ms{data_suffix}"
                    )
            self._schedule_ui_stall_log_write(timestamp, stall * 1000.0, suffix, extra_lines=extra_lines)
            try:
                self.log.warning("UI stall %.1f ms%s", stall * 1000.0, suffix)
            except Exception:
                pass
            self._ui_stall_watchdog_expected = now + self._ui_stall_watchdog_interval_s
            return
        if stall < -self._ui_stall_watchdog_interval_s:
            self._ui_stall_watchdog_expected = now + self._ui_stall_watchdog_interval_s
            return
        self._ui_stall_watchdog_expected = expected + self._ui_stall_watchdog_interval_s

    def _build_ui_stall_context(self) -> str:
        parts: list[str] = []
        now = time.perf_counter()
        try:
            focused = self.focused
        except Exception:
            focused = None
        focus_id = getattr(focused, "id", None)
        if focus_id:
            parts.append(f"focus={focus_id}")
        elif focused is not None:
            parts.append(f"focus={focused.__class__.__name__}")

        last_pane = getattr(self, "_last_active_pane", None)
        if last_pane:
            parts.append(f"pane={last_pane}")

        if getattr(self, "query_executing", False):
            parts.append("query=1")
        if getattr(self, "_connecting_config", None):
            parts.append("connect=1")
        if getattr(self, "_schema_indexing", False):
            parts.append("schema=1")
        if getattr(self, "_command_mode", False):
            parts.append("command=1")
        if getattr(self, "_tree_filter_visible", False):
            parts.append("tree_filter=1")
        if getattr(self, "_results_filter_visible", False):
            parts.append("results_filter=1")
        if getattr(self, "in_transaction", False):
            parts.append("tx=1")

        last_key = getattr(self, "_last_key", None)
        if last_key:
            parts.append(f"key={last_key}")
        last_char = getattr(self, "_last_key_char", None)
        if last_char and last_char.strip():
            parts.append(f"char={last_char}")
        if getattr(self, "_last_action", None):
            parts.append(f"action={self._last_action}")
            last_action_at = getattr(self, "_last_action_at", None)
            if last_action_at is not None:
                age_ms = max(0.0, (now - last_action_at) * 1000.0)
                parts.append(f"action_age={age_ms:.0f}ms")
        if getattr(self, "_last_command", None):
            parts.append(f"cmd=:{self._last_command}")
            last_command_at = getattr(self, "_last_command_at", None)
            if last_command_at is not None:
                age_ms = max(0.0, (now - last_command_at) * 1000.0)
                parts.append(f"cmd_age={age_ms:.0f}ms")

        try:
            if self.current_config:
                parts.append(f"conn={self.current_config.name}")
                parts.append(f"dbtype={self.current_config.db_type}")
        except Exception:
            pass
        try:
            if hasattr(self, "_get_effective_database"):
                db_name = self._get_effective_database()
                if db_name:
                    parts.append(f"db={db_name}")
        except Exception:
            pass
        try:
            node = self.object_tree.cursor_node
        except Exception:
            node = None
        if node and getattr(node, "data", None):
            try:
                kind = self._get_node_kind(node)
            except Exception:
                kind = None
            name = getattr(node.data, "name", None)
            if name and kind:
                parts.append(f"tree={kind}:{name}")
            elif name:
                parts.append(f"tree={name}")

        try:
            if hasattr(self, "_process_worker_client") and self._process_worker_client is not None:
                parts.append("worker=1")
            else:
                parts.append("worker=0")
        except Exception:
            pass
        try:
            runtime = getattr(self.services, "runtime", None)
            if runtime is not None:
                worker_setting = "1" if getattr(runtime, "process_worker", False) else "0"
                parts.append(f"worker_setting={worker_setting}")
        except Exception:
            pass

        try:
            if self.query_input is not None:
                text_len = len(self.query_input.text)
                parts.append(f"query_len={text_len}")
        except Exception:
            pass

        if not parts:
            return ""
        return f" ({', '.join(parts)})"

    def _schedule_ui_stall_log_write(
        self,
        timestamp: str,
        ms: float,
        suffix: str,
        *,
        extra_lines: list[str] | None = None,
    ) -> None:
        line = f"[{timestamp}] {ms:.1f} ms{suffix}"
        path = self._ui_stall_watchdog_log_path

        def work() -> None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.chmod(path.parent, 0o700)
                except OSError:
                    pass
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
                    if extra_lines:
                        for extra in extra_lines:
                            handle.write(extra + "\n")
            except Exception:
                pass

        try:
            self.run_worker(work, name="ui-stall-log", thread=True, exclusive=False)
        except Exception:
            pass

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
