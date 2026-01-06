"""Text-area related widgets for sqlit."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.events import Key
from textual.widgets import TextArea

if TYPE_CHECKING:
    from sqlit.shared.ui.protocols import AutocompleteProtocol


class QueryTextArea(TextArea):
    """TextArea that intercepts clipboard keys and defers Enter to app."""

    _INSERT_CURSOR_COLOR = "#91C58D"
    _last_text: str = ""
    _terminal_cursor_active: bool = False

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
            driver.write(f"\x1b]12;{self._INSERT_CURSOR_COLOR}\x1b\\")
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
