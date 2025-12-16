"""A simple modal message screen (no buttons)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

from ...widgets import Dialog


class MessageScreen(ModalScreen):
    """Modal screen that shows a message and closes via keyboard."""

    BINDINGS = [
        Binding("enter", "close", "Continue"),
        Binding("escape", "close", "Close", show=False),
    ]

    CSS = """
    MessageScreen {
        align: center middle;
        background: transparent;
    }

    #message-dialog {
        width: 60;
        max-width: 80%;
        border: solid $primary;
        border-subtitle-color: $primary;
    }

    #message-content {
        padding: 1;
    }

    #message-content.flash {
        background: $primary 30%;
    }
    """

    def __init__(self, title: str, message: str):
        super().__init__()
        self._title = title
        self.message = message

    def compose(self) -> ComposeResult:
        shortcuts = [("Continue", "<enter>")]
        with Dialog(id="message-dialog", title=self._title, shortcuts=shortcuts):
            yield Static(self.message, id="message-content")

    def action_close(self) -> None:
        self.dismiss()

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        # Prevent underlying screens from receiving actions when another modal is on top.
        if self.app.screen is not self:
            return False
        return super().check_action(action, parameters)
