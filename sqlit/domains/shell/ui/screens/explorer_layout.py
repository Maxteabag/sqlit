"""Choose the explorer hierarchy without editing a configuration file."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from sqlit.shared.ui.widgets import Dialog


class ExplorerLayoutScreen(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel", priority=True)]
    CSS = """
    ExplorerLayoutScreen { align: center middle; background: transparent; }
    #explorer-layout-dialog { width: 72; height: auto; }
    #explorer-layout-description { margin: 0 1 1 1; color: $text-muted; }
    #explorer-layout-options { height: 8; border: none; padding: 0 1; }
    #explorer-layout-note { margin: 1; color: $text-muted; }
    """

    def __init__(self, current: str, *, supported: bool | None):
        super().__init__()
        self.current = current
        self.supported = supported

    def compose(self) -> ComposeResult:
        with Dialog(id="explorer-layout-dialog", title="Explorer Layout", shortcuts=[("Apply", "<enter>"), ("Cancel", "<esc>")]):
            yield Static("Choose how you browse database objects. Your choice is saved.", id="explorer-layout-description")
            yield OptionList(
                Option("By object type (default)\nDatabase → Tables / Views → Schema\nCompare the same object type across schemas.", id="type"),
                Option("By schema\nDatabase → Schema → Tables / Views\nKeep one schema's related objects together.", id="schema"),
                id="explorer-layout-options",
            )
            note = "SQLite and providers without schema grouping keep their existing layout."
            if self.supported is False:
                note = "This connection keeps its existing layout. The saved choice applies to supported databases."
            yield Static(note, id="explorer-layout-note")

    def on_mount(self) -> None:
        options = self.query_one(OptionList)
        options.highlighted = 1 if self.current == "schema" else 0
        options.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def action_cancel(self) -> None:
        self.dismiss(None)
