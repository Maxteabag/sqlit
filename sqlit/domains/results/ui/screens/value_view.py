"""Value view screen for displaying cell contents."""

from __future__ import annotations

from typing import Any

from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from sqlit.shared.ui.widgets import Dialog


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
    """

    def __init__(self, value: str, title: str = "Value"):
        super().__init__()
        self._raw_value = value
        self._display_value = self._format_value(value)
        self.title = title

    @property
    def value(self) -> str:
        return self._raw_value

    def _format_value(self, value: str) -> str | Syntax:
        """Try to format value as JSON with syntax highlighting."""
        import ast
        import json

        stripped = value.strip()
        if stripped and stripped[0] in "{[":
            try:
                parsed = json.loads(stripped)
                formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
                return Syntax(formatted, "json", theme="ansi_dark", word_wrap=True)
            except (json.JSONDecodeError, ValueError):
                pass
            try:
                parsed = ast.literal_eval(stripped)
                formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
                return Syntax(formatted, "json", theme="ansi_dark", word_wrap=True)
            except (ValueError, SyntaxError):
                pass
        return value

    def compose(self) -> ComposeResult:
        shortcuts = [("Copy", "y"), ("Close", "<enter>")]
        with Dialog(id="value-dialog", title=self.title, shortcuts=shortcuts), VerticalScroll(id="value-scroll"):
            yield Static(self._display_value, id="value-text", markup=False)

    def on_mount(self) -> None:
        self.query_one("#value-scroll").focus()

    def action_dismiss(self) -> None:  # type: ignore[override]
        self.dismiss(None)

    def action_copy(self) -> None:
        from sqlit.shared.ui.widgets import flash_widget

        copied = getattr(self.app, "_copy_text", None)
        if callable(copied):
            copied(self.value)
            flash_widget(self.query_one("#value-text"))
        else:
            self.notify("Copy unavailable", timeout=2)
