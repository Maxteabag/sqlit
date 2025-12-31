"""Inline value viewer widget for sqlit."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.events import Key
from textual.widgets import Static

if TYPE_CHECKING:
    from sqlit.shared.ui.protocols import UINavigationProtocol


class InlineValueView(VerticalScroll):
    """Inline widget for viewing a cell value, replaces results table when active."""

    DEFAULT_CSS = """
    InlineValueView {
        display: none;
        height: 1fr;
        padding: 1;
        background: $surface;
    }

    InlineValueView.visible {
        display: block;
    }

    InlineValueView #value-content {
        width: auto;
        height: auto;
    }
    """

    can_focus = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._raw_value: str = ""  # Original unformatted value
        self._column_name: str = ""

    def on_key(self, event: Key) -> None:
        """Handle key events when value view is visible."""
        if not self.is_visible:
            return

        key = event.key
        app = cast("UINavigationProtocol", self.app)

        # Close value view
        if key in ("escape", "q"):
            app.action_close_value_view()
            event.prevent_default()
            event.stop()
            return

        # Copy value
        if key == "y":
            app.action_copy_value_view()
            event.prevent_default()
            event.stop()
            return

    def compose(self) -> ComposeResult:
        yield Static("", id="value-content")

    def set_value(self, value: str, column_name: str = "") -> None:
        """Set the value to display."""
        self._raw_value = value
        self._column_name = column_name
        self._rebuild()

    def _format_value(self, value: str, wrap_width: int = 100) -> str:
        """Try to format value as JSON or Python literal if possible.

        Long plain text strings are wrapped at wrap_width characters.
        """
        import ast
        import json
        import textwrap

        stripped = value.strip()
        # Check if it looks like JSON/dict/list (starts with { or [)
        if stripped and stripped[0] in "{[":
            # Try JSON first
            try:
                parsed = json.loads(stripped)
                return json.dumps(parsed, indent=2, ensure_ascii=False)
            except (json.JSONDecodeError, ValueError):
                pass
            # Try Python literal (handles single quotes, True/False/None)
            try:
                parsed = ast.literal_eval(stripped)
                return json.dumps(parsed, indent=2, ensure_ascii=False)
            except (ValueError, SyntaxError):
                pass

        # Wrap long plain text strings
        if len(value) > wrap_width and "\n" not in value:
            return textwrap.fill(value, width=wrap_width)

        return value

    def _rebuild(self) -> None:
        """Rebuild the display with dynamic width based on viewport."""
        try:
            # Get current width, accounting for padding (1 on each side)
            wrap_width = max(self.size.width - 2, 20) if self.size.width > 0 else 100
            formatted = self._format_value(self._raw_value, wrap_width)
            self.query_one("#value-content", Static).update(formatted)
        except Exception:
            pass

    def on_resize(self, event: Any) -> None:
        """Re-wrap text when widget is resized."""
        if self.is_visible:
            self._rebuild()

    def show(self) -> None:
        """Show the value view."""
        self.add_class("visible")
        # Add class to parent to hide results table via CSS
        if self.parent:
            self.parent.add_class("value-view-active")
        self.scroll_home(animate=False)
        self.focus()

    def hide(self) -> None:
        """Hide the value view."""
        self.remove_class("visible")
        # Remove class from parent to show results table again
        if self.parent:
            self.parent.remove_class("value-view-active")

    @property
    def is_visible(self) -> bool:
        """Check if value view is visible."""
        return "visible" in self.classes

    @property
    def value(self) -> str:
        """Get the current raw value (for copying)."""
        return self._raw_value
