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
    _sidebar_width: int | None = None
    _query_height: int | None = None

    # Pane resize bounds (cells)
    _SIDEBAR_MIN = 15
    _SIDEBAR_MAX = 80
    _QUERY_MIN = 5
    _RESIZE_STEP = 4

    def _set_fullscreen_mode(self: UINavigationMixinHost, mode: str) -> None:
        """Set fullscreen mode: none|explorer|query|results."""
        self._fullscreen_mode = mode
        self.screen.remove_class("results-fullscreen")
        self.screen.remove_class("query-fullscreen")
        self.screen.remove_class("explorer-fullscreen")

        if mode == "none":
            # Restore any user-chosen pane sizes; inline styles were cleared
            # when entering fullscreen so the fullscreen CSS rules could win.
            self.apply_persisted_pane_sizes()
        else:
            # Inline .styles beat stylesheet rules, so a resized pane would
            # ignore the fullscreen layout. Drop the inline sizes while
            # maximized; they are re-applied on the way back to "none".
            self._clear_inline_pane_sizes()

        if mode == "results":
            self.screen.add_class("results-fullscreen")
        elif mode == "query":
            self.screen.add_class("query-fullscreen")
        elif mode == "explorer":
            self.screen.add_class("explorer-fullscreen")

    def _clear_inline_pane_sizes(self: UINavigationMixinHost) -> None:
        """Remove inline width/height so fullscreen CSS rules apply cleanly."""
        try:
            self.sidebar.styles.clear_rule("width")
        except Exception:
            pass
        try:
            self.query_area.styles.clear_rule("height")
        except Exception:
            pass

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

    # ========================================================================
    # Pane resizing
    # ========================================================================

    def _pane_cells(self: UINavigationMixinHost, widget: Any, dim: str, fallback: int) -> int:
        """Return the current size of a pane dimension in cells.

        Reads the inline style value when it is already expressed in cells,
        otherwise falls back to the rendered size (handles the initial CSS
        rules that use ``%``/``fr`` units).
        """
        from textual.css.scalar import Unit

        scalar = getattr(widget.styles, dim, None)
        if scalar is not None and getattr(scalar, "unit", None) == Unit.CELLS:
            try:
                return int(scalar.value)
            except (TypeError, ValueError):
                pass
        size = getattr(widget, "size", None)
        measured = getattr(size, dim, None) if size is not None else None
        try:
            measured = int(measured)
        except (TypeError, ValueError):
            measured = 0
        return measured if measured > 0 else fallback

    def _resize_step_amount(self: UINavigationMixinHost, base: int) -> int:
        """Multiply the base step by any pending vim count prefix."""
        count = self._get_and_clear_count() or 1
        return base * count

    def _resize_sidebar(self: UINavigationMixinHost, delta: int, *, persist: bool = True) -> None:
        """Grow/shrink the explorer sidebar width by ``delta`` cells."""
        if self._fullscreen_mode != "none" or self.screen.has_class("explorer-hidden"):
            return
        current = self._pane_cells(self.sidebar, "width", 35)
        new = max(self._SIDEBAR_MIN, min(self._SIDEBAR_MAX, current + delta))
        if new == current:
            return
        self.sidebar.styles.width = new
        self._sidebar_width = new
        if persist:
            self._persist_pane_sizes()

    def _resize_split(self: UINavigationMixinHost, delta: int, *, persist: bool = True) -> None:
        """Move the query/results split by ``delta`` cells (query pane height)."""
        if self._fullscreen_mode != "none":
            return
        panel = getattr(self.main_panel, "size", None)
        panel_height = int(getattr(panel, "height", 0) or 0)
        upper = max(self._QUERY_MIN, panel_height - self._QUERY_MIN)
        current = self._pane_cells(self.query_area, "height", 10)
        new = max(self._QUERY_MIN, min(upper, current + delta))
        if new == current:
            return
        self.query_area.styles.height = new
        self._query_height = new
        if persist:
            self._persist_pane_sizes()

    def _resize_active_pane(self: UINavigationMixinHost, delta: int) -> None:
        """Resize whichever boundary belongs to the focused pane."""
        if self.object_tree.has_focus:
            self._resize_sidebar(delta)
        else:
            self._resize_split(delta)

    def action_grow_active_pane(self: UINavigationMixinHost) -> None:
        """Grow the focused pane (leader command)."""
        self._resize_active_pane(self._RESIZE_STEP)

    def action_shrink_active_pane(self: UINavigationMixinHost) -> None:
        """Shrink the focused pane (leader command)."""
        self._resize_active_pane(-self._RESIZE_STEP)

    def action_grow_sidebar(self: UINavigationMixinHost) -> None:
        """Widen the explorer sidebar."""
        self._resize_sidebar(self._resize_step_amount(self._RESIZE_STEP))

    def action_shrink_sidebar(self: UINavigationMixinHost) -> None:
        """Narrow the explorer sidebar."""
        self._resize_sidebar(self._resize_step_amount(-self._RESIZE_STEP))

    def action_grow_split(self: UINavigationMixinHost) -> None:
        """Give the query pane more height (results shrinks)."""
        self._resize_split(self._resize_step_amount(self._RESIZE_STEP))

    def action_shrink_split(self: UINavigationMixinHost) -> None:
        """Give the results pane more height (query shrinks)."""
        self._resize_split(self._resize_step_amount(-self._RESIZE_STEP))

    def _persist_pane_sizes(self: UINavigationMixinHost) -> None:
        """Save the current pane sizes so they survive a restart."""
        try:
            store = self.services.settings_store
            if self._sidebar_width is not None:
                store.set("sidebar_width", self._sidebar_width)
            if self._query_height is not None:
                store.set("query_area_height", self._query_height)
        except Exception:
            pass

    def apply_persisted_pane_sizes(self: UINavigationMixinHost) -> None:
        """Re-apply stored pane sizes on startup, clamped to current bounds."""
        width = self._sidebar_width
        if width is not None:
            clamped = max(self._SIDEBAR_MIN, min(self._SIDEBAR_MAX, int(width)))
            self._sidebar_width = clamped
            try:
                self.sidebar.styles.width = clamped
            except Exception:
                pass
        height = self._query_height
        if height is not None:
            try:
                self.query_area.styles.height = max(self._QUERY_MIN, int(height))
            except Exception:
                pass

    def action_quit(self: UINavigationMixinHost) -> None:
        """Quit the application."""
        close_worker = getattr(self, "_close_process_worker_client", None)
        if callable(close_worker):
            try:
                close_worker()
            except Exception:
                pass
        self.exit()

    def action_show_help(self: UINavigationMixinHost) -> None:
        """Show help with all keybindings."""
        from ..screens import HelpScreen

        sections = self._state_machine.generate_help_sections()
        ctx = self._get_input_context()
        active_section_id = self._state_machine.get_active_help_section_id(ctx)
        self.push_screen(HelpScreen(sections, active_section_id))

    def action_show_keybinding_editor(self: UINavigationMixinHost) -> None:
        """Open the in-app keybinding editor."""
        from ..screens import KeybindingEditorScreen

        self.push_screen(KeybindingEditorScreen())

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
