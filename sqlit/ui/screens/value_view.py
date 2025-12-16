"""Value view screen for displaying cell contents."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from ...widgets import Dialog


class ValueViewScreen(ModalScreen):
    """Modal screen for viewing a single (potentially long) value."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("enter", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("y", "copy", "Copy"),
    ]

    CSS = """
    ValueViewScreen {
        align: center middle;
        background: transparent;
    }

    #value-dialog {
        width: 90;
        height: 70%;
    }

    #value-scroll {
        height: 1fr;
        border: solid $primary-darken-2;
        padding: 1;
    }

    #value-text {
        width: auto;
        height: auto;
    }

    #value-text.flash-copy {
        background: $success;
    }
    """

    def __init__(self, value: str, title: str = "Value"):
        super().__init__()
        self.value = self._format_value(value)
        self.title = title

    def _format_value(self, value: str) -> str:
        """Try to format value as JSON or Python literal if possible."""
        import ast
        import json

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
        return value

    def compose(self) -> ComposeResult:
        shortcuts = [("Copy", "y"), ("Close", "<enter>")]
        with Dialog(id="value-dialog", title=self.title, shortcuts=shortcuts):
            with VerticalScroll(id="value-scroll"):
                yield Static(self.value, id="value-text")

    def on_mount(self) -> None:
        self.query_one("#value-scroll").focus()

    def action_dismiss(self) -> None:  # type: ignore[override]
        self.dismiss(None)

    def action_copy(self) -> None:
        copied = getattr(self.app, "_copy_text", None)
        if callable(copied):
            copied(self.value)
            self._flash_copy()
        else:
            self.notify("Copy unavailable", timeout=2)

    def _flash_copy(self) -> None:
        """Flash the text background to indicate copy."""
        text_area = self.query_one("#value-text")
        text_area.add_class("flash-copy")
        self.set_timer(0.15, lambda: text_area.remove_class("flash-copy"))
