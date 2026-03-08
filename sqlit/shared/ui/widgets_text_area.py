"""Text-area related widgets for sqlit."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from rich.segment import Segment
from textual.color import Color
from textual.events import Key
from textual.strip import Strip
from textual.widgets import TextArea

if TYPE_CHECKING:
    from sqlit.shared.ui.protocols import AutocompleteProtocol


class QueryTextArea(TextArea):
    """TextArea that intercepts clipboard keys and defers Enter to app."""

    _last_text: str = ""
    _terminal_cursor_active: bool = False
    _relative_line_numbers: bool = False
    _last_cursor_row: int = -1

    # Normalize OS-variant shortcuts to canonical forms
    # Maps: super → ctrl for common operations, strips shift where irrelevant
    _KEY_NORMALIZATION: dict[str, str] = {
        # Paste variants
        "super+v": "ctrl+v",
        "ctrl+shift+v": "ctrl+v",
        "super+shift+v": "ctrl+v",
        # Copy variants
        "super+c": "ctrl+c",
        "ctrl+shift+c": "ctrl+c",
        "super+shift+c": "ctrl+c",
        # Cut variants
        "super+x": "ctrl+x",
        "ctrl+shift+x": "ctrl+x",
        "super+shift+x": "ctrl+x",
        # Select all variants
        "super+a": "ctrl+a",
        # Undo variants
        "super+z": "ctrl+z",
        # Redo variants
        "super+y": "ctrl+y",
        "super+shift+z": "ctrl+y",  # macOS-style redo
        "ctrl+shift+z": "ctrl+y",   # Alternative redo
        # Backspace/delete - shift shouldn't change behavior
        "shift+backspace": "backspace",
        "shift+delete": "delete",
    }

    def _normalize_key(self, key: str) -> str:
        """Normalize OS-variant shortcuts to canonical form."""
        return self._KEY_NORMALIZATION.get(key, key)

    def _is_insert_mode(self) -> bool:
        """Check if app is in vim INSERT mode."""
        from sqlit.core.vim import VimMode
        vim_mode = getattr(self.app, "vim_mode", None)
        return vim_mode == VimMode.INSERT

    def _should_use_terminal_cursor(self) -> bool:
        """Use a terminal bar cursor only in INSERT mode with focus."""
        return self.has_focus and self._is_insert_mode()

    def _get_insert_cursor_color(self) -> str:
        from sqlit.domains.shell.app.themes import DEFAULT_MODE_COLORS, MODE_NORMAL_COLOR_VAR

        theme = self.app.current_theme
        variables = getattr(theme, "variables", {}) or {}
        theme_key = "dark" if theme.dark else "light"
        default = DEFAULT_MODE_COLORS[theme_key][MODE_NORMAL_COLOR_VAR]
        return str(variables.get(MODE_NORMAL_COLOR_VAR, default))

    def _format_osc_color(self, value: str) -> str | None:
        value = value.strip()
        if not value:
            return None
        try:
            color = Color.parse(value)
        except Exception:
            return None
        hex_value = color.hex
        if hex_value.startswith("ansi_"):
            return None
        return hex_value

    def _sync_terminal_cursor(self) -> None:
        """Show/hide a terminal bar cursor based on insert mode and focus."""
        use_terminal = self._should_use_terminal_cursor()
        if use_terminal == self._terminal_cursor_active:
            return

        self._terminal_cursor_active = use_terminal
        self._line_cache.clear()
        self.refresh()

        driver = getattr(self.app, "_driver", None)
        if driver is None:
            return

        if use_terminal:
            # Show cursor and request steady bar shape (DECSCUSR 6).
            driver.write("\x1b[?25h\x1b[6 q")
            osc_color = self._format_osc_color(self._get_insert_cursor_color())
            if osc_color:
                driver.write(f"\x1b]12;{osc_color}\x1b\\")
        else:
            # Hide cursor and reset to steady block (DECSCUSR 2).
            driver.write("\x1b[?25l\x1b[2 q")
            driver.write("\x1b]112\x1b\\")
        driver.flush()

    def sync_terminal_cursor(self) -> None:
        """Public hook to refresh cursor rendering."""
        self._sync_terminal_cursor()

    @property
    def _draw_cursor(self) -> bool:  # type: ignore[override]
        if self._should_use_terminal_cursor():
            return False
        return super()._draw_cursor

    def _watch_has_focus(self, focus: bool) -> None:
        super()._watch_has_focus(focus)
        self._sync_terminal_cursor()

    async def _on_key(self, event: Key) -> None:
        """Intercept clipboard, undo/redo, and Enter keys."""
        normalized_key = self._normalize_key(event.key)

        # Clipboard shortcuts only work in INSERT mode (vim consistency)
        if normalized_key in ("ctrl+a", "ctrl+c", "ctrl+v"):
            if not self._is_insert_mode():
                # Block these in normal mode - use vim commands instead
                event.prevent_default()
                event.stop()
                return

            # Handle CTRL+A (select all) - override Emacs beginning-of-line
            if normalized_key == "ctrl+a":
                if hasattr(self.app, "action_select_all"):
                    self.app.action_select_all()
                event.prevent_default()
                event.stop()
                return

            # Handle CTRL+C (copy) - override default behavior
            if normalized_key == "ctrl+c":
                if hasattr(self.app, "action_copy_selection"):
                    self.app.action_copy_selection()
                event.prevent_default()
                event.stop()
                return

            # Handle CTRL+V (paste) - override default behavior
            if normalized_key == "ctrl+v":
                # Push undo state before paste
                self._push_undo_if_changed()
                if hasattr(self.app, "action_paste"):
                    self.app.action_paste()
                event.prevent_default()
                event.stop()
                return

        # Undo/redo work in both modes
        # Handle CTRL+Z (undo)
        if normalized_key == "ctrl+z":
            if hasattr(self.app, "action_undo"):
                self.app.action_undo()
            event.prevent_default()
            event.stop()
            return

        # Handle CTRL+Y (redo)
        if normalized_key == "ctrl+y":
            if hasattr(self.app, "action_redo"):
                self.app.action_redo()
            event.prevent_default()
            event.stop()
            return

        # Note: Shift+Arrow selection is handled natively by TextArea
        # (shift+left/right/up/down, shift+home/end)

        # Handle Enter key when autocomplete is visible
        if event.key == "enter":
            app = cast("AutocompleteProtocol", self.app)
            if getattr(app, "_autocomplete_visible", False):
                # Hide autocomplete and suppress re-triggering from the newline
                if hasattr(app, "_hide_autocomplete"):
                    app._hide_autocomplete()
                app._suppress_autocomplete_on_newline = True

        # For text-modifying keys, push undo state before the change
        if self._is_text_modifying_key(normalized_key):
            self._push_undo_if_changed()

        # For all other keys, use default TextArea behavior
        await super()._on_key(event)

    def _is_text_modifying_key(self, key: str) -> bool:
        """Check if a key might modify text (expects normalized key)."""
        # Single characters, backspace, delete, enter are text-modifying
        if len(key) == 1:
            return True
        return key in ("backspace", "delete", "enter", "tab")

    def _push_undo_if_changed(self) -> None:
        """Push current state to undo history if text has changed."""
        current_text = self.text
        if current_text != self._last_text:
            if hasattr(self.app, "_push_undo_state"):
                self.app._push_undo_state()
            self._last_text = current_text

    @property
    def relative_line_numbers(self) -> bool:
        """Whether to show relative line numbers."""
        return self._relative_line_numbers

    @relative_line_numbers.setter
    def relative_line_numbers(self, value: bool) -> None:
        """Set relative line numbers mode."""
        if self._relative_line_numbers != value:
            self._relative_line_numbers = value
            self._line_cache.clear()
            self.refresh()

    def _watch_selection(self, previous_selection: object, selection: object) -> None:
        """Clear line cache when cursor row changes (for relative line numbers)."""
        super()._watch_selection(previous_selection, selection)  # type: ignore[arg-type]
        if self._relative_line_numbers and self.show_line_numbers:
            # Get current cursor row
            cursor_row = self.selection.end[0]
            if cursor_row != self._last_cursor_row:
                self._last_cursor_row = cursor_row
                self._line_cache.clear()
                self.refresh()

    def render_line(self, y: int) -> Strip:
        """Render a line, with relative line numbers if enabled."""
        # Get the base rendered line
        strip = super().render_line(y)

        # If relative line numbers not enabled, return as-is
        if not self._relative_line_numbers or not self.show_line_numbers:
            return strip

        # Get line info
        scroll_y = self.scroll_offset[1]
        absolute_y = scroll_y + y
        cursor_row = self.selection.end[0]
        gutter_width = self.gutter_width

        if gutter_width == 0:
            return strip

        # Get the wrapped document info to check if this is a continuation line
        wrapped_document = self.wrapped_document
        if absolute_y >= wrapped_document.height:
            return strip

        try:
            line_info = wrapped_document._offset_to_line_info[absolute_y]
        except (IndexError, AttributeError):
            return strip

        if line_info is None:
            return strip

        line_index, section_offset = line_info

        # Only show line number on first section of wrapped lines
        if section_offset != 0:
            return strip

        # Calculate the relative/absolute line number to display
        if line_index == cursor_row:
            # Current line shows absolute number
            line_num = line_index + self.line_number_start
        else:
            # Other lines show relative distance
            line_num = abs(line_index - cursor_row)

        # Format the new gutter content
        gutter_width_no_margin = gutter_width - 2
        new_gutter_text = f"{line_num:>{gutter_width_no_margin}}  "

        # Replace the gutter segment in the strip
        segments = list(strip._segments)
        if segments:
            # The first segment should be the gutter
            old_seg = segments[0]
            if len(old_seg.text) == gutter_width:
                segments[0] = Segment(new_gutter_text, old_seg.style)
                return Strip(segments, strip.cell_length)

        return strip
