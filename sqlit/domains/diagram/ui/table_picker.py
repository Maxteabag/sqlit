"""Table picker modal for ER diagram generation."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from sqlit.shared.ui.widgets import Dialog


class DiagramTablePicker(ModalScreen[list[str] | None]):
    """Modal to select tables for ER diagram generation."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False, priority=True),
    ]

    CSS = """
    DiagramTablePicker {
        align: center middle;
        background: transparent;
    }

    #diagram-picker-dialog {
        width: 60;
        max-width: 80%;
        max-height: 80%;
    }

    #diagram-picker-body {
        height: auto;
        max-height: 100%;
    }

    #diagram-picker-input {
        margin-bottom: 1;
    }

    #diagram-picker-list {
        height: auto;
        max-height: 30;
        border: none;
    }

    #diagram-picker-list > .option-list--option {
        padding: 0;
    }

    #diagram-picker-status {
        height: 1;
        margin-top: 1;
        color: $text-muted;
        text-align: right;
    }
    """

    def __init__(self, tables: list[str]) -> None:
        super().__init__()
        self._tables = sorted(tables)
        self._selected: set[str] = set()
        self._filter_text = ""

    def compose(self) -> ComposeResult:
        shortcuts = [("Toggle", "<space>"), ("Toggle All", "a"), ("OK", "<enter>")]
        with Dialog(id="diagram-picker-dialog", title="Select Tables for Diagram", shortcuts=shortcuts):
            with Vertical(id="diagram-picker-body"):
                yield Input(placeholder="Filter tables...", id="diagram-picker-input")
                yield OptionList(*self._build_options(), id="diagram-picker-list")
                yield Static(self._status_text(), id="diagram-picker-status")

    def _build_options(self) -> list[Option]:
        options: list[Option] = []
        for table in self._tables:
            if self._filter_text and self._filter_text.lower() not in table.lower():
                continue
            check = "[*]" if table in self._selected else "[ ]"
            options.append(Option(f"{check} {table}", id=table))
        return options

    def _status_text(self) -> str:
        return f"{len(self._selected)}/{len(self._tables)} selected"

    def _rebuild(self) -> None:
        option_list = self.query_one("#diagram-picker-list", OptionList)
        highlighted = option_list.highlighted
        option_list.clear_options()
        for opt in self._build_options():
            option_list.add_option(opt)
        if highlighted is not None and highlighted < option_list.option_count:
            option_list.highlighted = highlighted
        self.query_one("#diagram-picker-status", Static).update(self._status_text())

    def on_mount(self) -> None:
        self.query_one("#diagram-picker-list", OptionList).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "diagram-picker-input":
            self._filter_text = event.value
            self._rebuild()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "diagram-picker-input":
            option_list = self.query_one("#diagram-picker-list", OptionList)
            option_list.focus()

    def _toggle_highlighted(self) -> None:
        option_list = self.query_one("#diagram-picker-list", OptionList)
        if option_list.highlighted is not None:
            opt = option_list.get_option_at_index(option_list.highlighted)
            table_name = opt.id or ""
            if table_name:
                if table_name in self._selected:
                    self._selected.discard(table_name)
                else:
                    self._selected.add(table_name)
                self._rebuild()

    def on_key(self, event: Any) -> None:
        key = getattr(event, "key", "")
        focused = self.app.focused
        input_widget = self.query_one("#diagram-picker-input", Input)
        option_list = self.query_one("#diagram-picker-list", OptionList)
        in_input = focused is input_widget

        if key == "enter" and not in_input:
            self._confirm()
            event.prevent_default()
            event.stop()
        elif key == "tab" and in_input:
            option_list.focus()
            event.prevent_default()
            event.stop()
        elif key == "slash" and not in_input:
            input_widget.focus()
            event.prevent_default()
            event.stop()
        elif key == "space" and not in_input:
            self._toggle_highlighted()
            event.prevent_default()
            event.stop()
        elif key == "j" and not in_input:
            option_list.action_cursor_down()
            event.prevent_default()
            event.stop()
        elif key == "k" and not in_input:
            option_list.action_cursor_up()
            event.prevent_default()
            event.stop()
        elif key == "a" and not in_input:
            if len(self._selected) == len(self._tables):
                self._selected.clear()
            else:
                self._selected = set(self._tables)
            self._rebuild()
            event.prevent_default()
            event.stop()

    def _confirm(self) -> None:
        if self._selected:
            self.dismiss(sorted(self._selected))
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if self.app.screen is not self:
            return False
        return super().check_action(action, parameters)
