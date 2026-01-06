"""Status and notification helpers for UI navigation."""

from __future__ import annotations

from typing import Any

from sqlit.domains.connections.providers.metadata import get_connection_display_info
from sqlit.shared.ui.protocols import UINavigationMixinHost


class UIStatusMixin:
    """Mixin providing status bar and footer updates."""

    _notification_timer: Any | None = None
    _last_notification: str = ""
    _last_notification_severity: str = "information"
    _last_notification_time: str = ""
    _notification_history: list[tuple[str, str, str]] = []
    _last_active_pane: str | None = None
    def _update_section_labels(self: UINavigationMixinHost) -> None:
        """Update section labels to highlight the active pane."""
        try:
            pane_explorer = self.query_one("#sidebar")
            pane_query = self.query_one("#query-area")
            pane_results = self.query_one("#results-area")
        except Exception:
            return

        # Find which pane is focused
        active_pane = None
        focused = self.focused
        if focused:
            widget = focused
            while widget:
                widget_id = getattr(widget, "id", None)
                if widget_id == "object-tree" or widget_id == "sidebar":
                    active_pane = "explorer"
                    break
                elif widget_id == "query-input" or widget_id == "query-area":
                    active_pane = "query"
                    break
                elif widget_id == "results-table" or widget_id == "results-area":
                    active_pane = "results"
                    break
                widget = getattr(widget, "parent", None)

        # Only update labels if a pane is focused (don't clear when dialogs are open)
        if active_pane:
            self._last_active_pane = active_pane

        # Update active-pane class based on dialog state
        # When dialog is open, remove active-pane class (border reverts to default)
        # but title text will stay primary via explicit markup in _sync_active_pane_title
        dialog_open = bool(getattr(self, "_dialog_open", False))
        pane_explorer.remove_class("active-pane")
        pane_query.remove_class("active-pane")
        pane_results.remove_class("active-pane")

        if not dialog_open:
            last_active = getattr(self, "_last_active_pane", None)
            if last_active == "explorer":
                pane_explorer.add_class("active-pane")
            elif last_active == "query":
                pane_query.add_class("active-pane")
            elif last_active == "results":
                pane_results.add_class("active-pane")

        self._sync_active_pane_title()

    def _sync_active_pane_title(self: UINavigationMixinHost) -> None:
        """Adjust pane title color when dialogs are open.

        Keybinding hints [e], [q], [r] are:
        - White by default (inactive pane)
        - Primary when pane is selected
        - White when dialog is open (keybindings disabled)

        The pane title (Explorer, Query, Results) uses CSS border-title-color:
        - $border (white) for inactive panes
        - $primary for active pane (via .active-pane class)
        """
        try:
            pane_explorer = self.query_one("#sidebar")
            pane_query = self.query_one("#query-area")
            pane_results = self.query_one("#results-area")
        except Exception:
            return

        dialog_open = bool(getattr(self, "_dialog_open", False))
        active_pane = getattr(self, "_last_active_pane", None)

        direct_config = getattr(self, "_direct_connection_config", None)
        direct_active = (
            direct_config is not None
            and self.current_config is not None
            and direct_config.name == self.current_config.name
        )
        explorer_label = "Direct connection" if direct_active else "Explorer"

        def set_title(pane: Any, key: str, label: str, *, active: bool) -> None:
            if active and dialog_open:
                # Active pane with dialog: key matches border (disabled), title stays primary
                # Border reverts to default (active-pane class removed)
                pane.border_title = f"[$border]\\[{key}][/] [$primary]{label}[/]"
            elif active:
                # Active pane, no dialog: both key and title primary
                pane.border_title = f"[$primary]\\[{key}] {label}[/]"
            else:
                # Inactive pane: key and title match border color via CSS
                pane.border_title = f"\\[{key}] {label}"

        set_title(pane_explorer, "e", explorer_label, active=active_pane == "explorer")
        set_title(pane_query, "q", "Query", active=active_pane == "query")
        set_title(pane_results, "r", "Results", active=active_pane == "results")

    def _update_vim_mode_visuals(self: UINavigationMixinHost) -> None:
        """Update all visual indicators based on current vim mode.

        This updates:
        - Border color on query pane (orange for NORMAL, green for INSERT)
        - Cursor color (via CSS class)
        - Status bar mode indicator

        Only shows vim mode indicators when query pane has focus.
        """
        from sqlit.core.vim import VimMode

        try:
            query_area = self.query_one("#query-area")
            has_query_focus = self.query_input.has_focus
        except Exception:
            return

        # Update CSS classes for border and cursor color
        # Only show vim mode colors when query pane has focus
        query_area.remove_class("vim-normal", "vim-insert")
        if has_query_focus:
            if self.vim_mode == VimMode.NORMAL:
                query_area.add_class("vim-normal")
            else:
                query_area.add_class("vim-insert")

        try:
            query_input = self.query_input
        except Exception:
            query_input = None
        if query_input is not None and hasattr(query_input, "sync_terminal_cursor"):
            query_input.sync_terminal_cursor()

        # Also update the status bar
        self._update_status_bar()

    def _update_status_bar(self: UINavigationMixinHost) -> None:
        """Update status bar with connection and vim mode info."""
        from sqlit.core.vim import VimMode
        from sqlit.shared.ui.spinner import SPINNER_FRAMES

        try:
            status = self.status_bar
        except Exception:
            return
        # Hide connection info while query is executing
        direct_config = getattr(self, "_direct_connection_config", None)
        direct_active = (
            direct_config is not None
            and self.current_config is not None
            and direct_config.name == self.current_config.name
        )

        connecting_config = getattr(self, "_connecting_config", None)

        if connecting_config is not None:
            connect_spinner = getattr(self, "_connect_spinner", None)
            spinner = connect_spinner.frame if connect_spinner else SPINNER_FRAMES[0]
            source_emoji = connecting_config.get_source_emoji()
            conn_info = f"[#FBBF24]{spinner} Connecting to {source_emoji}{connecting_config.name}[/]"
        elif getattr(self, "_connection_failed", False):
            conn_info = "[#ff6b6b]Connection failed[/]"
        elif self.current_config:
            source_emoji = self.current_config.get_source_emoji()
            conn_info = f"[#4ADE80]Connected to {source_emoji}{self.current_config.name}[/]"
            if direct_active:
                conn_info += " [dim](direct, not saved)[/]"
        else:
            conn_info = "Not connected"

        if getattr(self, "_command_mode", False):
            from rich.markup import escape as escape_markup

            cmd_buffer = escape_markup(getattr(self, "_command_buffer", ""))
            conn_info = f"[bold cyan]:{cmd_buffer}[/]"

        # Build status indicators
        status_parts = []

        # Check if schema is indexing (only show during debugging)
        schema_spinner = getattr(self, "_schema_spinner", None)
        if schema_spinner and schema_spinner.running:
            if getattr(self, "_debug_mode", False) or getattr(self, "_debug_idle_scheduler", False):
                status_parts.append(f"[bold cyan]{schema_spinner.frame} Indexing...[/]")

        # Check if in a transaction
        if getattr(self, "in_transaction", False):
            status_parts.append("[bold magenta]⚡ TRANSACTION[/]")

        status_str = "  ".join(status_parts)
        if status_str:
            status_str += "  "

        # Build left side content - mode indicator is always preserved
        mode_str = ""
        mode_plain = ""
        try:
            if self.query_input.has_focus:
                if self.vim_mode == VimMode.NORMAL:
                    # Warm beige background for NORMAL mode
                    mode_str = "[bold #1e1e1e on #D8C499] NORMAL [/]  "
                    mode_plain = " NORMAL   "
                else:
                    # Soft green background for INSERT mode
                    mode_str = "[bold #1e1e1e on #91C58D] INSERT [/]  "
                    mode_plain = " INSERT   "
        except Exception:
            pass

        left_content = f"{status_str}{mode_str}{conn_info}"

        notification = getattr(self, "_last_notification", "")
        timestamp = getattr(self, "_last_notification_time", "")
        severity = getattr(self, "_last_notification_severity", "information")
        launch_ms = getattr(self, "_launch_ms", None)
        show_launch = (
            getattr(self, "_debug_mode", False)
            and isinstance(launch_ms, (int, float))
            and not self.current_config
            and not getattr(self, "_connection_failed", False)
        )
        launch_str = f"[dim]Launched in {launch_ms:.0f}ms[/]" if show_launch else ""
        launch_plain = f"Launched in {launch_ms:.0f}ms" if show_launch else ""

        # Combine right-side content
        right_str = launch_str
        right_plain = launch_plain

        import re

        try:
            total_width = self.size.width - 2
        except Exception:
            total_width = 80

        left_plain = re.sub(r"\[.*?\]", "", left_content)

        # Build right side content - executing status takes priority over notification
        if getattr(self, "query_executing", False):
            from sqlit.core.state_base import resolve_display_key

            cancel_key = resolve_display_key("cancel_operation") or "<esc>"
            query_spinner = getattr(self, "_query_spinner", None)
            if query_spinner and query_spinner.running:
                import time

                from sqlit.shared.core.utils import format_duration_ms

                start_time = getattr(self, "_query_start_time", None)
                if start_time:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    elapsed_str = format_duration_ms(elapsed_ms, always_seconds=True)
                    right_content = (
                        f"[bold yellow]{query_spinner.frame} Executing [{elapsed_str}][/] "
                        f"[dim]{cancel_key} to cancel[/]"
                    )
                    right_content_plain = f"  Executing [{elapsed_str}] {cancel_key} to cancel"
                else:
                    right_content = f"[bold yellow]{query_spinner.frame} Executing[/] [dim]{cancel_key} to cancel[/]"
                    right_content_plain = f"  Executing {cancel_key} to cancel"
            else:
                right_content = "[bold yellow]Executing...[/]"
                right_content_plain = "Executing..."

            gap = total_width - len(left_plain) - len(right_content_plain)
            if gap > 2:
                status.update(f"{left_content}{' ' * gap}{right_content}")
            else:
                status.update(f"{left_content}  {right_content}")
        elif notification:
            # Show notification right-aligned
            time_prefix = f"[dim]{timestamp}[/] " if timestamp else ""

            if severity == "warning":
                notif_str = f"{time_prefix}[#f0c674]{notification}[/]"
            else:
                notif_str = f"{time_prefix}{notification}"

            notif_plain = f"{timestamp} {notification}" if timestamp else notification
            gap = total_width - len(left_plain) - len(notif_plain)
            if gap > 2:
                status.update(f"{left_content}{' ' * gap}{notif_str}")
            else:
                status.update(f"{left_content}  {notif_str}")
        elif right_str:
            gap = total_width - len(left_plain) - len(right_plain)
            if gap > 2:
                status.update(f"{left_content}{' ' * gap}{right_str}")
            else:
                status.update(f"{left_content}  {right_str}")
        else:
            status.update(left_content)

    def _update_idle_scheduler_bar(self: UINavigationMixinHost) -> None:
        """Update the idle scheduler debug bar."""
        if not getattr(self, "_debug_idle_scheduler", False):
            return

        try:
            bar = self.idle_scheduler_bar
        except Exception:
            return

        from sqlit.domains.shell.app.idle_scheduler import get_idle_scheduler

        scheduler = get_idle_scheduler()
        if not scheduler:
            bar.update("[dim]Idle Scheduler: Not initialized[/]")
            return

        pending = scheduler.pending_jobs
        is_idle = scheduler.is_idle
        completed = scheduler._jobs_completed
        work_time = scheduler._total_work_time_ms

        if pending > 0 and is_idle:
            status = "[bold cyan]⚡ WORKING[/]"
            details = f"[bold]{pending}[/] jobs pending"
        elif pending > 0 and not is_idle:
            status = "[yellow]⏸ POSTPONED[/]"
            details = f"[bold]{pending}[/] jobs waiting for you to stop"
        elif is_idle:
            status = "[dim]💤 IDLE[/]"
            details = "waiting for work"
        else:
            status = "[dim]👆 USER ACTIVE[/]"
            details = "no pending work"

        bar.update(
            f"{status}  │  {details}  │  "
            f"[dim]{completed} completed[/]  │  "
            f"[dim]{work_time:.0f}ms worked[/]"
        )

    def notify(
        self: UINavigationMixinHost,
        message: str,
        *,
        title: str = "",
        severity: str = "information",
        timeout: float | None = None,
        markup: bool = True,
    ) -> None:
        """Show notification in status bar (takes over full bar temporarily).

        Args:
            message: The notification message.
            title: Unused.
            severity: One of "information", "warning", "error".
            timeout: Seconds before auto-clearing (default 3s, errors stay 5s).
        """
        from datetime import datetime

        # Cancel any existing timer
        if hasattr(self, "_notification_timer") and self._notification_timer is not None:
            self._notification_timer.stop()
            self._notification_timer = None

        timestamp = datetime.now().strftime("%H:%M:%S")
        self._notification_history.append((timestamp, message, severity))

        if severity == "error":
            # Clear any status bar notification and show error in results
            self._last_notification = ""
            self._last_notification_severity = "information"
            self._last_notification_time = ""
            self._update_status_bar()
            self._show_error_in_results(message, timestamp)
            self._show_error_dialog(message, title=title)
        else:
            # Show normal/warning in status bar
            self._last_notification = message
            self._last_notification_severity = severity
            self._last_notification_time = timestamp
            self._update_status_bar()

    def _show_error_dialog(self: UINavigationMixinHost, message: str, *, title: str = "") -> None:
        """Display an error dialog for critical errors."""
        from textual.screen import ModalScreen

        from sqlit.shared.ui.screens.error import ErrorScreen

        if any(isinstance(screen, ModalScreen) for screen in self.screen_stack[1:]):
            return
        dialog_title = title or "Error"
        self.push_screen(ErrorScreen(dialog_title, message))

    def _show_error_in_results(self: UINavigationMixinHost, message: str, timestamp: str) -> None:
        """Display error message in the results table."""
        import re

        error_text = f"[{timestamp}] {message}" if timestamp else message

        # Replace newlines and collapse multiple whitespace to single space
        # DataTable cells only show one line, so we flatten the error
        error_text = re.sub(r"\s+", " ", error_text).strip()

        self._last_result_columns = ["Error"]
        self._last_result_rows = [(error_text,)]
        self._last_result_row_count = 1

        self._replace_results_table(["Error"], [(error_text,)])
        self._update_footer_bindings()

    def _update_footer_bindings(self: UINavigationMixinHost) -> None:
        """Update footer with context-appropriate bindings from the state machine."""
        from sqlit.shared.ui.widgets import ContextFooter, KeyBinding

        try:
            footer = self.query_one(ContextFooter)
        except Exception:
            return

        if hasattr(self, "_get_input_context"):
            ctx = self._get_input_context()
        else:
            return

        left_display, right_display = self._state_machine.get_display_bindings(ctx)

        left_bindings = [KeyBinding(b.key, b.label, b.action) for b in left_display]
        right_bindings = [KeyBinding(b.key, b.label, b.action) for b in right_display]

        footer.set_bindings(left_bindings, right_bindings)
