"""A simple modal loading screen."""

from __future__ import annotations

from collections.abc import Callable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Vertical
from textual.screen import ModalScreen
from textual.widgets import Label
from textual.widgets._loading_indicator import LoadingIndicator


class LoadingScreen(ModalScreen[None]):
    """Screen to display a loading message with a spinner."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, message: str, *, on_cancel: Callable[[], None] | None = None):
        super().__init__()
        self.message = message
        self._on_cancel = on_cancel
        self._cancel_requested = False

    def compose(self) -> ComposeResult:
        yield Vertical(
            Center(LoadingIndicator(), classes="spinner-container"),
            Center(Label(self.message, id="loading-message")),
            classes="loading-dialog",
        )

    CSS = """
    LoadingScreen {
        align: center middle;
    }

    .loading-dialog {
        background: $surface;
        padding: 1 2;
        width: auto;
        height: auto;
        border: solid $primary;
    }
    """

    def action_cancel(self) -> None:
        if self._cancel_requested:
            return
        self._cancel_requested = True
        if self._on_cancel is not None:
            self._on_cancel()
        try:
            self.query_one("#loading-message", Label).update("Cancelling...")
        except Exception:
            pass
