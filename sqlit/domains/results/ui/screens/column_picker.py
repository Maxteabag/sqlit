"""Filterable column picker for jumping the results cursor to a specific column."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList
from textual.widgets.option_list import Option

from sqlit.shared.ui.widgets import Dialog


class ColumnPickerScreen(ModalScreen[int | None]):
    """Modal dialog that lets the user fuzzy-filter columns and pick one.

    Dismisses with the index of the chosen column (into the original list
    supplied at construction time), or `None` if cancelled.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("enter", "submit", "Jump", show=False),
        Binding("down", "cursor_down", "Next", show=False),
        Binding("up", "cursor_up", "Previous", show=False),
        Binding("ctrl+j", "cursor_down", "Next", show=False),
        Binding("ctrl+k", "cursor_up", "Previous", show=False),
    ]

    CSS = """
    ColumnPickerScreen {
        align: center middle;
        background: transparent;
    }

    #column-picker-dialog {
        width: 50;
        max-width: 80%;
        height: auto;
        max-height: 22;
    }

    #column-picker-body {
        height: auto;
        max-height: 20;
    }

    #column-picker-input {
        height: 3;
        border: solid $panel;
        background: $surface;
    }

    #column-picker-input:focus {
        border: solid $primary;
    }

    #column-picker-list {
        height: auto;
        max-height: 14;
        border: none;
        background: $surface;
    }
    """

    def __init__(self, columns: list[str]) -> None:
        super().__init__()
        self._columns = columns
        self._filtered: list[tuple[int, str]] = list(enumerate(columns))

    def compose(self) -> ComposeResult:
        shortcuts: list[tuple[str, str]] = [("Jump", "<enter>"), ("Cancel", "<esc>")]
        with Dialog(id="column-picker-dialog", title="Jump to column", shortcuts=shortcuts):
            with Vertical(id="column-picker-body"):
                yield Input(placeholder="Filter...", id="column-picker-input")
                yield OptionList(*self._render_options(), id="column-picker-list")

    def on_mount(self) -> None:
        self.query_one("#column-picker-input", Input).focus()

    def _render_options(self) -> list[Option]:
        return [Option(name, id=str(idx)) for idx, name in self._filtered]

    def _rebuild_options(self, query: str) -> None:
        needle = query.strip().lower()
        if needle:
            self._filtered = [
                (idx, name) for idx, name in enumerate(self._columns) if needle in name.lower()
            ]
        else:
            self._filtered = list(enumerate(self._columns))
        option_list = self.query_one("#column-picker-list", OptionList)
        option_list.clear_options()
        for option in self._render_options():
            option_list.add_option(option)
        if self._filtered:
            option_list.highlighted = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "column-picker-input":
            self._rebuild_options(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "column-picker-input":
            self._submit_highlighted()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = event.option.id
        if option_id is not None:
            try:
                self.dismiss(int(option_id))
                return
            except ValueError:
                pass
        self.dismiss(None)

    def action_cursor_down(self) -> None:
        option_list = self.query_one("#column-picker-list", OptionList)
        if option_list.option_count:
            option_list.action_cursor_down()

    def action_cursor_up(self) -> None:
        option_list = self.query_one("#column-picker-list", OptionList)
        if option_list.option_count:
            option_list.action_cursor_up()

    def action_submit(self) -> None:
        self._submit_highlighted()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit_highlighted(self) -> None:
        option_list = self.query_one("#column-picker-list", OptionList)
        if not self._filtered:
            self.dismiss(None)
            return
        highlighted = option_list.highlighted if option_list.highlighted is not None else 0
        highlighted = max(0, min(highlighted, len(self._filtered) - 1))
        idx, _name = self._filtered[highlighted]
        self.dismiss(idx)

    def check_action(self, action: str, parameters: Any) -> bool | None:
        if self.app.screen is not self:
            return False
        return super().check_action(action, parameters)
