"""UI navigation mixin for SSMSTUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.widgets import DataTable, Static, TextArea, Tree

if TYPE_CHECKING:
    from ...widgets import VimMode


class UINavigationMixin:
    """Mixin providing UI navigation and vim mode functionality."""

    # These attributes are defined in the main app class
    vim_mode: "VimMode"
    current_connection: Any
    current_config: Any
    _fullscreen_mode: str
    _last_notification: str
    _last_notification_severity: str
    _last_notification_time: str
    _notification_timer: Any
    _notification_history: list
    _leader_timer: Any
    _leader_pending: bool

    def _set_fullscreen_mode(self, mode: str) -> None:
        """Set fullscreen mode: none|explorer|query|results."""
        self._fullscreen_mode = mode
        self.screen.remove_class("results-fullscreen")
        self.screen.remove_class("query-fullscreen")
        self.screen.remove_class("explorer-fullscreen")

        if mode == "results":
            self.screen.add_class("results-fullscreen")
        elif mode == "query":
            self.screen.add_class("query-fullscreen")
        elif mode == "explorer":
            self.screen.add_class("explorer-fullscreen")

    def _update_section_labels(self) -> None:
        """Update section labels to highlight the active pane."""
        try:
            label_explorer = self.query_one("#label-explorer", Static)
            label_query = self.query_one("#label-query", Static)
            label_results = self.query_one("#label-results", Static)
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
            label_explorer.remove_class("active")
            label_query.remove_class("active")
            label_results.remove_class("active")
            if active_pane == "explorer":
                label_explorer.add_class("active")
            elif active_pane == "query":
                label_query.add_class("active")
            elif active_pane == "results":
                label_results.add_class("active")

    def action_focus_explorer(self) -> None:
        """Focus the Object Explorer pane."""
        if self._fullscreen_mode != "none":
            self._set_fullscreen_mode("none")
        # Unhide explorer if hidden
        if self.screen.has_class("explorer-hidden"):
            self.screen.remove_class("explorer-hidden")
        self.object_tree.focus()
        # If no node selected or on root, move cursor to first child
        if self.object_tree.cursor_node is None or self.object_tree.cursor_node == self.object_tree.root:
            if self.object_tree.root.children:
                self.object_tree.cursor_line = 0

    def action_focus_query(self) -> None:
        """Focus the Query pane (in NORMAL mode)."""
        from ...widgets import VimMode

        if self._fullscreen_mode != "none":
            self._set_fullscreen_mode("none")
        self.vim_mode = VimMode.NORMAL
        self.query_input.read_only = True
        self.query_input.focus()
        self._update_status_bar()

    def action_focus_results(self) -> None:
        """Focus the Results pane."""
        if self._fullscreen_mode != "none":
            self._set_fullscreen_mode("none")
        self.results_table.focus()

    def action_enter_insert_mode(self) -> None:
        """Enter INSERT mode for query editing."""
        from ...widgets import VimMode

        if self.query_input.has_focus and self.vim_mode == VimMode.NORMAL:
            self.vim_mode = VimMode.INSERT
            self.query_input.read_only = False
            self._update_status_bar()
            self._update_footer_bindings()

    def action_exit_insert_mode(self) -> None:
        """Exit INSERT mode, return to NORMAL mode."""
        from ...widgets import VimMode

        if self.vim_mode == VimMode.INSERT:
            self.vim_mode = VimMode.NORMAL
            self.query_input.read_only = True
            self._hide_autocomplete()
            self._update_status_bar()
            self._update_footer_bindings()

    def _update_status_bar(self) -> None:
        """Update status bar with connection and vim mode info."""
        from ...widgets import VimMode
        from .query import SPINNER_FRAMES

        status = self.status_bar
        if getattr(self, "_connection_failed", False):
            conn_info = "[#ff6b6b]Connection failed[/]"
        elif self.current_config:
            display_info = self.current_config.get_display_info()
            conn_info = f"[#90EE90]Connected to {self.current_config.name}[/] ({display_info})"
        else:
            conn_info = "Not connected"

        # Build status indicators
        status_parts = []

        # Check if schema is indexing
        if getattr(self, "_schema_indexing", False):
            spinner_idx = getattr(self, "_schema_spinner_index", 0)
            spinner = SPINNER_FRAMES[spinner_idx % len(SPINNER_FRAMES)]
            status_parts.append(f"[bold cyan]{spinner} Indexing...[/]")

        # Check if query is executing
        if getattr(self, "_query_executing", False):
            import time

            spinner_idx = getattr(self, "_spinner_index", 0)
            spinner = SPINNER_FRAMES[spinner_idx % len(SPINNER_FRAMES)]
            start_time = getattr(self, "_query_start_time", None)
            if start_time:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                if elapsed_ms >= 1000:
                    elapsed_str = f"{elapsed_ms / 1000:.1f}s"
                else:
                    elapsed_str = f"{elapsed_ms:.0f}ms"
                status_parts.append(f"[bold yellow]{spinner} Executing [{elapsed_str}][/] [dim]<space>z to cancel[/]")
            else:
                status_parts.append(f"[bold yellow]{spinner} Executing[/] [dim]<space>z to cancel[/]")

        status_str = "  ".join(status_parts)
        if status_str:
            status_str += "  "

        # Build left side content
        try:
            if self.query_input.has_focus:
                if self.vim_mode == VimMode.NORMAL:
                    mode_str = f"[bold orange1]-- {self.vim_mode.value} --[/]"
                else:
                    mode_str = f"[dim]-- {self.vim_mode.value} --[/]"
                left_content = f"{status_str}{mode_str}  {conn_info}"
            else:
                left_content = f"{status_str}{conn_info}"
        except Exception:
            left_content = f"{status_str}{conn_info}"

        notification = getattr(self, "_last_notification", "")
        timestamp = getattr(self, "_last_notification_time", "")
        severity = getattr(self, "_last_notification_severity", "information")

        if notification:
            # Normal/warning notifications on right side
            import re
            left_plain = re.sub(r'\[.*?\]', '', left_content)
            time_prefix = f"[dim]{timestamp}[/] " if timestamp else ""

            if severity == "warning":
                notif_str = f"{time_prefix}[#f0c674]{notification}[/]"
            else:
                notif_str = f"{time_prefix}{notification}"

            notif_plain = f"{timestamp} {notification}" if timestamp else notification

            try:
                total_width = self.size.width - 2
            except Exception:
                total_width = 80

            gap = total_width - len(left_plain) - len(notif_plain)
            if gap > 2:
                status.update(f"{left_content}{' ' * gap}{notif_str}")
            else:
                status.update(f"{left_content}  {notif_str}")
        else:
            status.update(left_content)

    def notify(
        self,
        message: str,
        *,
        title: str = "",
        severity: str = "information",
        timeout: float = 3.0,
    ) -> None:
        """Show notification in status bar (takes over full bar temporarily).

        Args:
            message: The notification message.
            title: Ignored (for API compatibility).
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
        else:
            # Show normal/warning in status bar
            self._last_notification = message
            self._last_notification_severity = severity
            self._last_notification_time = timestamp
            self._update_status_bar()

    def _show_error_in_results(self, message: str, timestamp: str) -> None:
        """Display error message in the results table."""
        import textwrap

        error_text = f"[{timestamp}] {message}" if timestamp else message

        # Wrap to table width (minus some padding), minimum 40 chars
        wrap_width = max(40, self.results_table.size.width - 4)
        wrapped = textwrap.fill(error_text, width=wrap_width)

        self._last_result_columns = ["Error"]
        self._last_result_rows = [(wrapped,)]
        self._last_result_row_count = 1

        self.results_table.clear(columns=True)
        self.results_table.add_column("Error")
        self.results_table.add_row(wrapped)
        self._update_footer_bindings()

    def action_toggle_explorer(self) -> None:
        """Toggle the visibility of the explorer sidebar."""
        if self._fullscreen_mode != "none":
            self._set_fullscreen_mode("none")
            self.object_tree.focus()
            return

        if self.screen.has_class("explorer-hidden"):
            self.screen.remove_class("explorer-hidden")
            self.object_tree.focus()
        else:
            # If explorer has focus, move focus to query before hiding
            if self.object_tree.has_focus:
                self.query_input.focus()
            self.screen.add_class("explorer-hidden")

    def action_change_theme(self) -> None:
        """Open the theme selection dialog."""
        from ..screens import ThemeScreen

        def on_theme_selected(theme: str | None) -> None:
            if theme:
                self.theme = theme

        self.push_screen(ThemeScreen(self.theme), on_theme_selected)

    def action_toggle_fullscreen(self) -> None:
        """Toggle fullscreen for the currently focused pane."""
        if self.object_tree.has_focus:
            target = "explorer"
        elif self.query_input.has_focus:
            target = "query"
        elif self.results_table.has_focus:
            target = "results"
        else:
            target = "none"

        if target != "none" and self._fullscreen_mode == target:
            self._set_fullscreen_mode("none")
        else:
            self._set_fullscreen_mode(target)

        if self._fullscreen_mode == "explorer":
            self.object_tree.focus()
        elif self._fullscreen_mode == "query":
            self.query_input.focus()
        elif self._fullscreen_mode == "results":
            self.results_table.focus()

        self._update_section_labels()
        self._update_footer_bindings()

    def _update_footer_bindings(self) -> None:
        """Update footer with context-appropriate bindings from the state machine."""
        from ...widgets import ContextFooter, KeyBinding

        try:
            footer = self.query_one(ContextFooter)
        except Exception:
            return

        left_display, right_display = self._state_machine.get_display_bindings(self)

        left_bindings = [
            KeyBinding(b.key, b.label, b.action) for b in left_display
        ]
        right_bindings = [
            KeyBinding(b.key, b.label, b.action) for b in right_display
        ]

        footer.set_bindings(left_bindings, right_bindings)

    def action_show_help(self) -> None:
        """Show help with all keybindings."""
        from ..screens import HelpScreen

        help_text = self._state_machine.generate_help_text()
        self.push_screen(HelpScreen(help_text))

    def action_leader_key(self) -> None:
        """Handle leader key (space) press - show command menu after delay."""
        from ...widgets import VimMode

        # Don't trigger in INSERT mode
        if self.vim_mode == VimMode.INSERT:
            return

        # Cancel any existing timer
        if hasattr(self, "_leader_timer") and self._leader_timer is not None:
            self._leader_timer.stop()

        self._leader_pending = True

        def show_menu():
            if getattr(self, "_leader_pending", False):
                self._leader_pending = False
                self._show_leader_menu()

        # Show menu after 200ms delay
        self._leader_timer = self.set_timer(0.2, show_menu)

    def _cancel_leader_pending(self) -> None:
        """Cancel leader pending state and timer."""
        self._leader_pending = False
        if hasattr(self, "_leader_timer") and self._leader_timer is not None:
            self._leader_timer.stop()
            self._leader_timer = None

    def _execute_leader_command(self, action: str) -> None:
        """Execute a leader command by action name."""
        if action == "quit":
            self.exit()
            return
        action_method = getattr(self, f"action_{action}", None)
        if action_method:
            action_method()

    def _show_leader_menu(self) -> None:
        """Display the leader menu."""
        from textual.screen import ModalScreen

        from ..screens import LeaderMenuScreen

        if any(isinstance(screen, ModalScreen) for screen in self.screen_stack[1:]):
            return

        self.push_screen(LeaderMenuScreen(), self._handle_leader_result)

    def _handle_leader_result(self, result: str | None) -> None:
        """Handle result from leader menu."""
        self._update_footer_bindings()
        if result:
            self._execute_leader_command(result)

    def action_leader_toggle_explorer(self) -> None:
        self._execute_leader_command("toggle_explorer")

    def action_leader_toggle_fullscreen(self) -> None:
        self._execute_leader_command("toggle_fullscreen")

    def action_leader_show_connection_picker(self) -> None:
        self._execute_leader_command("show_connection_picker")

    def action_leader_disconnect(self) -> None:
        self._execute_leader_command("disconnect")

    def action_leader_cancel_operation(self) -> None:
        self._execute_leader_command("cancel_operation")

    def action_leader_change_theme(self) -> None:
        self._execute_leader_command("change_theme")

    def action_leader_show_help(self) -> None:
        self._execute_leader_command("show_help")

    def action_leader_quit(self) -> None:
        self._execute_leader_command("quit")

    def on_descendant_focus(self, event) -> None:
        """Handle focus changes to update section labels and footer."""
        from ...widgets import VimMode

        self._update_section_labels()
        if not self.query_input.has_focus and self.vim_mode == VimMode.INSERT:
            self.vim_mode = VimMode.NORMAL
            self.query_input.read_only = True
        self._update_footer_bindings()
        self._update_status_bar()

    def on_descendant_blur(self, event) -> None:
        """Handle blur to update section labels."""
        self.call_later(self._update_section_labels)
