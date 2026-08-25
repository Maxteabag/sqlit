"""Name prompt used by Save Query and Save Query As."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from sqlit.shared.ui.widgets import Dialog


class SavedQueryNameScreen(ModalScreen[str | None]):
    """Prompt for a path relative to the current connection's library."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("enter", "save", "Save", priority=True),
    ]

    CSS = """
    SavedQueryNameScreen { align: center middle; background: transparent; }
    #saved-query-name-dialog { width: 64; max-width: 92%; height: auto; }
    #saved-query-name-description { color: $text-muted; margin-bottom: 1; }
    #saved-query-name-error { color: $error; height: 1; margin-top: 1; }
    #saved-query-name-input { border: solid $panel; }
    #saved-query-name-input:focus { border: solid $primary; }
    """

    def __init__(self, *, initial_name: str = "", title: str = "Save Query") -> None:
        super().__init__()
        self.initial_name = initial_name
        self.title_text = title

    def compose(self) -> ComposeResult:
        with Dialog(
            id="saved-query-name-dialog",
            title=self.title_text,
            shortcuts=[("Save", "enter"), ("Cancel", "esc")],
        ):
            yield Static(
                "Name this query. Use folders such as reports/daily-sales.",
                id="saved-query-name-description",
            )
            yield Input(
                value=self.initial_name,
                placeholder="reports/daily-sales.sql",
                id="saved-query-name-input",
            )
            yield Static("", id="saved-query-name-error")

    def on_mount(self) -> None:
        field = self.query_one("#saved-query-name-input", Input)
        field.focus()
        field.cursor_position = len(field.value)

    def action_save(self) -> None:
        value = self.query_one("#saved-query-name-input", Input).value.strip()
        if not value:
            self.query_one("#saved-query-name-error", Static).update("Enter a query name")
            return
        self.dismiss(value)

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        self.action_save()

    def action_cancel(self) -> None:
        self.dismiss(None)
