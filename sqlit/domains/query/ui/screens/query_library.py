"""Search and preview saved SQL files for the active connection."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from sqlit.domains.query.store.saved_queries import SavedQueryEntry
from sqlit.shared.core.utils import fuzzy_match
from sqlit.shared.ui.widgets import Dialog


class QueryLibraryScreen(ModalScreen[SavedQueryEntry | None]):
    """Fuzzy-searchable saved-query library with SQL preview."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("q", "cancel", "Cancel"),
        Binding("enter", "select", "Open"),
        Binding("slash", "focus_filter", "Search"),
    ]

    CSS = """
    QueryLibraryScreen { align: center middle; background: transparent; }
    #query-library-dialog { width: 94; max-width: 94%; height: 82%; max-height: 92%; }
    #query-library-description { color: $text-muted; margin-bottom: 1; }
    #query-library-filter { border: solid $panel; margin-bottom: 1; }
    #query-library-filter:focus { border: solid $primary; }
    #query-library-list { height: 1fr; border: none; background: $surface; }
    #query-library-list > .option-list--option { padding: 0 1; }
    #query-library-empty { color: $text-muted; padding: 2; text-align: center; }
    #query-library-preview-container {
        height: 10; min-height: 10; max-height: 10;
        background: $surface-darken-1; padding: 1; margin-top: 1;
    }
    #query-library-preview { height: auto; }
    """

    def __init__(self, entries: list[SavedQueryEntry], connection_name: str) -> None:
        super().__init__()
        self.entries = entries
        self.connection_name = connection_name
        self._display_entries = list(entries)

    def compose(self) -> ComposeResult:
        with Dialog(
            id="query-library-dialog",
            title=f"Query Library — {self.connection_name}",
            shortcuts=[("Open", "enter"), ("Search", "/"), ("Close", "esc")],
        ):
            yield Static(
                "Saved SQL files for this connection. Opening a file never executes it.",
                id="query-library-description",
            )
            yield Input(placeholder="Search filenames and folders…", id="query-library-filter")
            if self.entries:
                yield OptionList(
                    *(Option(Text(entry.display_name), id=str(index)) for index, entry in enumerate(self.entries)),
                    id="query-library-list",
                )
            else:
                yield Static(
                    "No saved queries yet. Use Save Query to create the library.",
                    id="query-library-empty",
                )
            with VerticalScroll(id="query-library-preview-container"):
                yield Static("", id="query-library-preview")

    def on_mount(self) -> None:
        if self.entries:
            option_list = self.query_one("#query-library-list", OptionList)
            option_list.focus()
            option_list.highlighted = 0
            self._update_preview()
        else:
            self.query_one("#query-library-filter", Input).focus()

    def _matches(self, entry: SavedQueryEntry, query: str) -> bool:
        if not query:
            return True
        filename_match, _ = fuzzy_match(query, entry.relative_path)
        content_match, _ = fuzzy_match(query, entry.query)
        return filename_match or content_match

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "query-library-filter" or not self.entries:
            return
        query = event.value.strip()
        self._display_entries = [entry for entry in self.entries if self._matches(entry, query)]
        option_list = self.query_one("#query-library-list", OptionList)
        option_list.clear_options()
        for index, entry in enumerate(self._display_entries):
            option_list.add_option(Option(Text(entry.display_name), id=str(index)))
        option_list.highlighted = 0 if self._display_entries else None
        self._update_preview()

    def action_focus_filter(self) -> None:
        self.query_one("#query-library-filter", Input).focus()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id == "query-library-list":
            self._update_preview()

    def _selected_entry(self) -> SavedQueryEntry | None:
        try:
            option_list = self.query_one("#query-library-list", OptionList)
        except Exception:
            return None
        index = option_list.highlighted
        if index is None or index >= len(self._display_entries):
            return None
        return self._display_entries[index]

    def _update_preview(self) -> None:
        preview = self.query_one("#query-library-preview", Static)
        entry = self._selected_entry()
        preview.update(Text(entry.query) if entry else Text("No matching queries", style="dim"))

    def action_select(self) -> None:
        entry = self._selected_entry()
        if entry is not None:
            self.dismiss(entry)

    def on_option_list_option_selected(self, _event: OptionList.OptionSelected) -> None:
        self.action_select()

    def action_cancel(self) -> None:
        self.dismiss(None)
