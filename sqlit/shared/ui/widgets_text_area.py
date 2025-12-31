"""Text-area related widgets for sqlit."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.events import Key
from textual.widgets import TextArea

if TYPE_CHECKING:
    from sqlit.shared.ui.protocols import AutocompleteProtocol


class QueryTextArea(TextArea):
    """TextArea that intercepts clipboard keys and defers Enter to app."""

    _last_text: str = ""

    async def _on_key(self, event: Key) -> None:
        """Intercept clipboard, undo/redo, and Enter keys."""
        # Handle CTRL+A (select all) - override Emacs beginning-of-line
        if event.key == "ctrl+a":
            if hasattr(self.app, "action_select_all"):
                self.app.action_select_all()
            event.prevent_default()
            event.stop()
            return

        # Handle CTRL+C (copy) - override default behavior
        if event.key == "ctrl+c":
            if hasattr(self.app, "action_copy_selection"):
                self.app.action_copy_selection()
            event.prevent_default()
            event.stop()
            return

        # Handle CTRL+V (paste) - override default behavior
        if event.key == "ctrl+v":
            # Push undo state before paste
            self._push_undo_if_changed()
            if hasattr(self.app, "action_paste"):
                self.app.action_paste()
            event.prevent_default()
            event.stop()
            return

        # Handle CTRL+Z (undo)
        if event.key == "ctrl+z":
            if hasattr(self.app, "action_undo"):
                self.app.action_undo()
            event.prevent_default()
            event.stop()
            return

        # Handle CTRL+Y (redo)
        if event.key == "ctrl+y":
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
        if self._is_text_modifying_key(event.key):
            self._push_undo_if_changed()

        # For all other keys, use default TextArea behavior
        await super()._on_key(event)

    def _is_text_modifying_key(self, key: str) -> bool:
        """Check if a key might modify text."""
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
