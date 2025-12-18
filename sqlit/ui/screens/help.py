"""Help screen showing keyboard shortcuts."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from ...widgets import Dialog


class HelpScreen(ModalScreen):
    """Modal screen showing keyboard shortcuts and navigation tips."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("enter", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
    ]

    CSS = """
    HelpScreen {
        align: center middle;
        background: transparent;
    }

    #help-dialog {
        width: 60;
        max-width: 70%;
        max-height: 80%;
    }

    #help-scroll {
        height: auto;
        max-height: 100%;
        background: $surface;
        border: none;
        scrollbar-gutter: stable;
        color: white;
    }
    """

    def __init__(self, help_text: str):
        super().__init__()
        self.help_text = help_text

    def compose(self) -> ComposeResult:
        with Dialog(id="help-dialog", title="Help", shortcuts=[("Close", "<enter>")]):
            with VerticalScroll(id="help-scroll"):
                yield Static(self.help_text)

    def action_dismiss(self) -> None:  # type: ignore[override]
        self.dismiss(None)
