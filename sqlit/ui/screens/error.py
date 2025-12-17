"""Error dialog screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

from ...widgets import Dialog


class ErrorScreen(ModalScreen):
    """Modal screen for displaying error messages."""

    BINDINGS = [
        Binding("enter", "close", "Close"),
        Binding("escape", "close", "Close"),
        Binding("y", "copy_message", "Copy"),
    ]

    CSS = """
    ErrorScreen {
        align: center middle;
        background: transparent;
    }

    #error-dialog {
        width: 60;
        max-width: 80%;
        border: solid $error;
        border-subtitle-color: $error;
    }

    #error-message {
        padding: 1;
    }
    """

    def __init__(self, title: str, message: str):
        super().__init__()
        self.title_text = title
        self.message = message

    def compose(self) -> ComposeResult:
        shortcuts = [("Copy", "y"), ("Close", "<enter>")]
        with Dialog(id="error-dialog", title=self.title_text, shortcuts=shortcuts):
            yield Static(self.message, id="error-message")

    def action_close(self) -> None:
        self.dismiss()

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        # Prevent underlying screens from receiving actions when another modal is on top.
        if self.app.screen is not self:
            return False
        return super().check_action(action, parameters)

    def action_copy_message(self) -> None:
        from ...widgets import flash_widget

        self.app.copy_to_clipboard(self.message)
        flash_widget(self.query_one("#error-message", Static))
