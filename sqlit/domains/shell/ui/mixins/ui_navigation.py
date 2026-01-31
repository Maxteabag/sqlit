"""UI navigation mixin for SSMSTUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.timer import Timer

from sqlit.shared.ui.protocols import UINavigationMixinHost

from .ui_leader import UILeaderMixin
from .ui_status import UIStatusMixin

if TYPE_CHECKING:
    pass


class UINavigationMixin(UIStatusMixin, UILeaderMixin):
    """Mixin providing UI navigation and vim mode functionality."""

    _notification_timer: Timer | None = None
    _leader_timer: Timer | None = None
    _last_active_pane: str | None = None

    def _set_fullscreen_mode(self: UINavigationMixinHost, mode: str) -> None:
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

    def action_focus_explorer(self: UINavigationMixinHost) -> None:
        """Focus the Explorer pane."""
        self._clear_count_buffer()  # Clear any pending count prefix
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

    def action_focus_query(self: UINavigationMixinHost) -> None:
        """Focus the Query pane (in NORMAL mode)."""
        from sqlit.core.vim import VimMode

        self._clear_count_buffer()  # Clear any pending count prefix
        if self._fullscreen_mode != "none":
            self._set_fullscreen_mode("none")
        self.vim_mode = VimMode.NORMAL
        self.query_input.read_only = True
        self.query_input.focus()
        self._update_vim_mode_visuals()

    def action_focus_results(self: UINavigationMixinHost) -> None:
        """Focus the Results pane."""
        self._clear_count_buffer()  # Clear any pending count prefix
        if self._fullscreen_mode != "none":
            self._set_fullscreen_mode("none")
        if self.results_area.has_class("stacked-mode"):
            try:
                from sqlit.shared.ui.widgets import SqlitDataTable
                from sqlit.shared.ui.widgets_stacked_results import ResultSection, StackedResultsContainer

                container = self.query_one("#stacked-results", StackedResultsContainer)
                sections = list(container.query(ResultSection))
                if sections:
                    section = next((s for s in sections if not s.collapsed), sections[0])
                    if section.collapsed:
                        section.collapsed = False
                        section.scroll_visible()
                    table = section.query_one(SqlitDataTable)
                    table.focus()
                    return
            except Exception:
                pass
        try:
            self.results_table.focus()
        except Exception:
            # Results table may not exist yet (Lazy loading)
            pass

    def action_enter_insert_mode(self: UINavigationMixinHost) -> None:
        """Enter INSERT mode for query editing."""
        from sqlit.core.vim import VimMode

        if self.query_input.has_focus and self.vim_mode == VimMode.NORMAL:
            self.vim_mode = VimMode.INSERT
            self.query_input.read_only = False
            self._update_vim_mode_visuals()
            self._update_footer_bindings()

    def action_exit_insert_mode(self: UINavigationMixinHost) -> None:
        """Exit INSERT mode, return to NORMAL mode."""
        from sqlit.core.vim import VimMode

        self._clear_count_buffer()  # Clear any pending count prefix
        if self.vim_mode == VimMode.INSERT:
            self.vim_mode = VimMode.NORMAL
            self.query_input.read_only = True
            self._hide_autocomplete()
            self._update_vim_mode_visuals()
            self._update_footer_bindings()

    def action_toggle_explorer(self: UINavigationMixinHost) -> None:
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

    def action_change_theme(self: UINavigationMixinHost) -> None:
        """Open the theme selection dialog."""
        from ..screens import ThemeScreen

        def on_theme_selected(theme: str | None) -> None:
            if theme:
                self.theme = theme

        self.push_screen(ThemeScreen(self.theme), on_theme_selected)

    def action_toggle_fullscreen(self: UINavigationMixinHost) -> None:
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

    def action_quit(self: UINavigationMixinHost) -> None:
        """Quit the application."""
        self.exit()

    def action_show_help(self: UINavigationMixinHost) -> None:
        """Show help with all keybindings."""
        from ..screens import HelpScreen

        help_text = self._state_machine.generate_help_text()
        self.push_screen(HelpScreen(help_text))

    def action_toggle_process_worker(self: UINavigationMixinHost) -> None:
        """Toggle the process worker setting."""
        enabled = not bool(self.services.runtime.process_worker)
        self.services.runtime.process_worker = enabled
        try:
            self.services.settings_store.set("process_worker", enabled)
        except Exception:
            pass
        if enabled:
            schedule_warm = getattr(self, "_schedule_process_worker_warm", None)
            if callable(schedule_warm):
                schedule_warm()
        else:
            close_fn = getattr(self, "_close_process_worker_client", None)
            if callable(close_fn):
                close_fn()
        state = "enabled" if enabled else "disabled"
        self.notify(f"Process worker {state}")

    def on_descendant_focus(self: UINavigationMixinHost, event: Any) -> None:
        """Handle focus changes to update section labels and footer."""
        from sqlit.core.vim import VimMode

        self._update_section_labels()
        try:
            has_query_focus = self.query_input.has_focus
        except Exception:
            has_query_focus = False
        if not has_query_focus and self.vim_mode == VimMode.INSERT:
            self.vim_mode = VimMode.NORMAL
            try:
                self.query_input.read_only = True
            except Exception:
                pass
        self._update_footer_bindings()
        self._update_vim_mode_visuals()

    def on_descendant_blur(self: UINavigationMixinHost, event: Any) -> None:
        """Handle blur to update section labels."""
        self.call_later(self._update_section_labels)
