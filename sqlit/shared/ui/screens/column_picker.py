"""Column-picker modal used by copy/export actions."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import SelectionList
from textual.widgets.selection_list import Selection

from sqlit.shared.ui.widgets import Dialog


class _ColumnSelectionList(SelectionList):
    """SelectionList that releases Enter so the parent screen can confirm.

    Upstream binds Enter to toggle (alongside Space). The picker needs Enter
    to mean "Confirm", so we override BINDINGS to keep only Space for toggle.
    """

    BINDINGS = [Binding("space", "select")]


class ColumnPickerScreen(ModalScreen[list[int] | None]):
    """Pick which columns to include in a copy/export operation.

    Returns the list of selected column indices (preserving original order),
    or None on cancel.
    """

    BINDINGS = [
        Binding("enter", "confirm", "Confirm", show=False, priority=True),
        Binding("escape", "cancel", "Cancel", show=False, priority=True),
        Binding("a", "select_all", "Select all", show=False, priority=True),
        Binding("n", "deselect_all", "Deselect all", show=False, priority=True),
    ]

    CSS = """
    ColumnPickerScreen {
        align: center middle;
        background: transparent;
    }

    #column-picker-dialog {
        width: 70%;
        max-width: 100;
        min-width: 60;
        max-height: 80%;
    }

    #column-list {
        height: auto;
        max-height: 20;
        background: $surface;
    }
    """

    def __init__(
        self,
        columns: list[str],
        initial_selected: list[int] | None = None,
        *,
        title: str = "Select columns",
    ) -> None:
        super().__init__()
        self._columns = list(columns)
        if initial_selected is None:
            self._initial = set(range(len(columns)))
        else:
            self._initial = set(initial_selected)
        self._title = title

    def compose(self) -> ComposeResult:
        selections = [
            Selection(name, idx, idx in self._initial)
            for idx, name in enumerate(self._columns)
        ]
        shortcuts = [
            ("Confirm", "enter"),
            ("Toggle", "space"),
            ("All", "a"),
            ("None", "n"),
            ("Cancel", "esc"),
        ]
        with Dialog(id="column-picker-dialog", title=self._title, shortcuts=shortcuts):
            yield _ColumnSelectionList(*selections, id="column-list")

    def on_mount(self) -> None:
        self.query_one("#column-list", SelectionList).focus()

    def _selected_indices(self) -> list[int]:
        sel_list = self.query_one("#column-list", SelectionList)
        return sorted(int(v) for v in sel_list.selected)

    def action_confirm(self) -> None:
        indices = self._selected_indices()
        if not indices:
            self.app.notify("Select at least one column", severity="warning")
            return
        self.dismiss(indices)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_select_all(self) -> None:
        self.query_one("#column-list", SelectionList).select_all()

    def action_deselect_all(self) -> None:
        self.query_one("#column-list", SelectionList).deselect_all()

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if self.app.screen is not self:
            return False
        return super().check_action(action, parameters)
