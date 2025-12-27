"""Confirmation dialog screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from ...widgets import Dialog


class ConfirmScreen(ModalScreen):
    """Modal screen for confirmation dialogs."""

    BINDINGS = [
        Binding("y", "yes", "Yes", show=False),
        Binding("n", "no", "No", show=False),
        Binding("escape", "cancel", "Cancel", show=False, priority=True),
        Binding("enter", "select_option", "Select", show=False),
    ]

    CSS = """
    ConfirmScreen {
        align: center middle;
        background: transparent;
    }

    #confirm-dialog {
        width: 36;
    }

    #confirm-description {
        margin-bottom: 1;
        color: $text-muted;
    }

    #confirm-list {
        height: auto;
        border: none;
    }

    #confirm-list > .option-list--option {
        padding: 0;
    }
    """

    def __init__(
        self,
        title: str,
        description: str | None = None,
        *,
        yes_label: str = "Yes",
        no_label: str = "No",
    ):
        super().__init__()
        self.title_text = title
        self.description = description
        self.yes_label = yes_label
        self.no_label = no_label

    def compose(self) -> ComposeResult:
        shortcuts: list[tuple[str, str]] = [("Yes", "y"), ("No", "n")]
        with Dialog(id="confirm-dialog", title=self.title_text, shortcuts=shortcuts):
            if self.description:
                yield Static(self.description, id="confirm-description")
            option_list = OptionList(
                Option(self.yes_label, id="yes"),
                Option(self.no_label, id="no"),
                id="confirm-list",
            )
            yield option_list

    def on_mount(self) -> None:
        self.query_one("#confirm-list", OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id == "yes":
            self.dismiss(True)
        elif event.option.id == "no":
            self.dismiss(False)

    def action_select_option(self) -> None:
        option_list = self.query_one("#confirm-list", OptionList)
        if option_list.highlighted is not None:
            option_id = option_list.get_option_at_index(option_list.highlighted).id
            if option_id == "yes":
                self.dismiss(True)
            elif option_id == "no":
                self.dismiss(False)

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)

    def action_cancel(self) -> None:
        # Escape cancels without selecting Yes/No.
        self.dismiss(None)

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        # Prevent underlying screens from receiving actions when another modal is on top.
        if self.app.screen is not self:
            return False
        return super().check_action(action, parameters)
