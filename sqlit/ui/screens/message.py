"""A simple modal message screen (no buttons)."""

from __future__ import annotations

from collections.abc import Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

from ...widgets import Dialog


class MessageScreen(ModalScreen):
    """Modal screen that shows a message and closes via keyboard."""

    BINDINGS = [
        Binding("enter", "primary", "Continue", show=False),
        Binding("escape", "close", "Close", show=False),
    ]

    CSS = """
    MessageScreen {
        align: center middle;
        background: transparent;
    }

    #message-dialog {
        width: auto;
        min-width: 70;
        max-width: 95%;
        border: solid $primary;
        border-subtitle-color: $primary;
    }

    #message-content {
        padding: 1 2;
        color: $text;
    }
    """

    def __init__(
        self,
        title: str,
        message: str,
        *,
        enter_label: str = "Continue",
        on_enter: Callable[[], None] | None = None,
    ):
        super().__init__()
        self._title = title
        self.message = message
        self._enter_label = enter_label
        self._on_enter = on_enter

    def compose(self) -> ComposeResult:
        shortcuts = [(self._enter_label, "<enter>")]
        with Dialog(id="message-dialog", title=self._title, shortcuts=shortcuts):
            yield Static(self.message, id="message-content")

    def action_primary(self) -> None:
        if self._on_enter is not None:
            self._on_enter()
            return
        self.dismiss()

    def action_close(self) -> None:
        self.dismiss()

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        # Prevent underlying screens from receiving actions when another modal is on top.
        if self.app.screen is not self:
            return False
        return super().check_action(action, parameters)
