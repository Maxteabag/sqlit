"""Pick a terminal editor for 'Edit query in editor'.

Shown the first time the action is invoked, or whenever the saved
preference is missing from the filesystem. The result is the editor
command string (e.g. ``"nvim"``); the caller persists it to settings.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from sqlit.domains.query.app.editor import EditorEntry, detect_editors
from sqlit.shared.ui.widgets import Dialog


class EditorPickerScreen(ModalScreen[str | None]):
    """Modal list of terminal editors. Installed ones are selectable;
    missing ones render disabled."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("enter", "select", "Select"),
    ]

    CSS = """
    EditorPickerScreen {
        align: center middle;
        background: transparent;
    }

    #editor-picker-dialog {
        width: 60;
        max-width: 90%;
        height: auto;
        max-height: 24;
    }

    #editor-picker-description {
        margin-bottom: 1;
        color: $text-muted;
        height: auto;
    }

    #editor-picker-list {
        background: $surface;
        border: none;
        height: auto;
        max-height: 16;
    }
    """

    def __init__(self, *, entries: list[EditorEntry] | None = None) -> None:
        super().__init__()
        self._entries = entries if entries is not None else detect_editors()

    def compose(self) -> ComposeResult:
        shortcuts = [("Select", "<enter>"), ("Cancel", "<esc>")]
        with Dialog(
            id="editor-picker-dialog",
            title="Pick a terminal editor",
            shortcuts=shortcuts,
        ):
            yield Static(
                "Choose your preferred terminal editor. Missing entries are grayed out.",
                id="editor-picker-description",
            )
            yield OptionList(id="editor-picker-list")

    def on_mount(self) -> None:
        option_list = self.query_one("#editor-picker-list", OptionList)
        first_installed: int | None = None
        for idx, entry in enumerate(self._entries):
            label = self._format_label(entry)
            option = Option(label, id=entry.command, disabled=not entry.is_installed)
            option_list.add_option(option)
            if first_installed is None and entry.is_installed:
                first_installed = idx
        if first_installed is not None:
            option_list.highlighted = first_installed
        option_list.focus()

    @staticmethod
    def _format_label(entry: EditorEntry) -> str:
        if entry.is_installed:
            return f"{entry.display_name}  [dim]({entry.path})[/]"
        return f"[dim]{entry.display_name}  (not installed)[/]"

    def action_select(self) -> None:
        option_list = self.query_one("#editor-picker-list", OptionList)
        idx = option_list.highlighted
        if idx is None:
            return
        try:
            option = option_list.get_option_at_index(idx)
        except Exception:
            return
        if option is None or option.disabled or option.id is None:
            return
        self.dismiss(option.id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.disabled or event.option.id is None:
            return
        self.dismiss(event.option.id)

    def action_cancel(self) -> None:
        self.dismiss(None)
