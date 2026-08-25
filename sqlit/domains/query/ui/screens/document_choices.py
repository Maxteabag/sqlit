"""Choice dialogs protecting saved-query documents from data loss."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from sqlit.shared.ui.widgets import Dialog


class _DocumentChoiceScreen(ModalScreen[str | None]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("enter", "select", "Select"),
    ]
    CSS = """
    UnsavedQueryChangesScreen, ExternalQueryChangeScreen {
        align: center middle;
        background: transparent;
    }
    .document-choice-dialog { width: 66; max-width: 92%; height: auto; }
    UnsavedQueryChangesScreen .document-choice-dialog { width: 46; }
    .document-choice-description { color: $text-muted; margin-bottom: 1; }
    .document-choice-list { height: auto; border: none; }
    .document-choice-list > .option-list--option { padding: 0; }
    """

    title_text = "Query document"
    description = ""
    choices: tuple[tuple[str, str], ...] = ()

    def compose(self) -> ComposeResult:
        with Dialog(
            classes="document-choice-dialog",
            title=self.title_text,
            shortcuts=[("Select", "enter"), ("Cancel", "esc")],
        ):
            if self.description:
                yield Static(self.description, classes="document-choice-description")
            yield OptionList(
                *(Option(label, id=value) for value, label in self.choices),
                classes="document-choice-list",
            )

    def on_mount(self) -> None:
        option_list = self.query_one(OptionList)
        option_list.focus()
        option_list.highlighted = 0

    def action_select(self) -> None:
        option_list = self.query_one(OptionList)
        index = option_list.highlighted
        if index is None:
            return
        option_id = option_list.get_option_at_index(index).id
        self.dismiss(str(option_id) if option_id is not None else None)

    def on_option_list_option_selected(self, _event: OptionList.OptionSelected) -> None:
        self.action_select()

    def action_cancel(self) -> None:
        self.dismiss(None)


class UnsavedQueryChangesScreen(_DocumentChoiceScreen):
    """Prompt before replacing or closing a dirty query document."""

    title_text = "Unsaved query changes"
    choices = (
        ("save", "Save and continue"),
        ("discard", "Discard changes"),
        ("cancel", "Keep editing"),
    )

    def __init__(self, document_name: str) -> None:
        super().__init__()
        _ = document_name


class ExternalQueryChangeScreen(_DocumentChoiceScreen):
    """Resolve a save conflict with a file changed outside sqlit."""

    title_text = "Query changed on disk"
    choices = (
        ("reload", "Reload the version on disk"),
        ("overwrite", "Overwrite the file with this editor"),
        ("save_as", "Save as a different query"),
        ("cancel", "Cancel"),
    )

    def __init__(self, document_name: str) -> None:
        super().__init__()
        self.description = f"{document_name} changed after it was opened. Choose which version to keep."
