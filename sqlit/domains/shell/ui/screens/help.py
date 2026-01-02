"""Help screen showing keyboard shortcuts."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from sqlit.shared.ui.widgets import Dialog


class HelpScreen(ModalScreen):
    """Modal screen showing keyboard shortcuts and navigation tips."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("enter", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("j", "scroll_down", "Scroll down", show=False),
        Binding("k", "scroll_up", "Scroll up", show=False),
        Binding("g", "scroll_home", "Scroll to top", show=False),
        Binding("G", "scroll_end", "Scroll to bottom", show=False),
    ]

    CSS = """
    HelpScreen {
        align: center middle;
        background: transparent;
    }

    #help-dialog {
        width: 72;
        max-width: 90%;
        max-height: 85%;
    }

    #help-scroll {
        height: auto;
        max-height: 100%;
        background: $surface;
        border: none;
        scrollbar-gutter: stable;
        padding: 0 1;
    }
    """

    def __init__(self, help_text: str):
        super().__init__()
        self.help_text = help_text

    def compose(self) -> ComposeResult:
        with Dialog(id="help-dialog", title="Keyboard Shortcuts", shortcuts=[("Close", "<esc>"), ("Scroll", "j/k")]):
            with VerticalScroll(id="help-scroll"):
                yield Static(self.help_text, markup=True)

    def action_dismiss(self) -> None:  # type: ignore[override]
        self.dismiss(None)

    def action_scroll_down(self) -> None:
        self.query_one("#help-scroll", VerticalScroll).scroll_down()

    def action_scroll_up(self) -> None:
        self.query_one("#help-scroll", VerticalScroll).scroll_up()

    def action_scroll_home(self) -> None:
        self.query_one("#help-scroll", VerticalScroll).scroll_home()

    def action_scroll_end(self) -> None:
        self.query_one("#help-scroll", VerticalScroll).scroll_end()
