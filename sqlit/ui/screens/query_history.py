"""Query history screen."""

from __future__ import annotations

from datetime import datetime

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from ...stores.history import QueryHistoryEntry
from ...widgets import Dialog


class QueryHistoryScreen(ModalScreen):
    """Modal screen for query history selection."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("q", "cancel", "Cancel"),
        Binding("enter", "select", "Select"),
        Binding("d", "delete", "Delete"),
        Binding("asterisk", "toggle_star", "Star"),
    ]

    CSS = """
    QueryHistoryScreen {
        align: center middle;
        background: transparent;
    }

    #history-dialog {
        width: 90;
        max-width: 90%;
        height: 80%;
        max-height: 90%;
    }

    #history-scroll {
        height: 1fr;
        background: $surface;
        border: none;
    }

    #history-list {
        height: auto;
        background: $surface;
        border: none;
        padding: 0;
    }

    #history-list > .option-list--option {
        padding: 0 1;
    }

    #history-empty {
        text-align: center;
        color: $text-muted;
        padding: 2;
    }

    #history-preview-container {
        height: 8;
        min-height: 8;
        max-height: 8;
        background: $surface-darken-1;
        border: none;
        padding: 1;
        margin-top: 1;
    }

    #history-preview {
        height: auto;
    }
    """

    def __init__(self, history: list, connection_name: str, starred: set[str] | None = None):
        super().__init__()
        self.history = history  # list of QueryHistoryEntry
        self.connection_name = connection_name
        self.starred = starred or set()  # set of starred query strings
        self._merged_entries: list[QueryHistoryEntry] = []

    def _merge_entries(self) -> list[QueryHistoryEntry]:
        """Merge history entries with starred-only queries."""
        # Mark history entries that are starred
        history_queries: set[str] = set()
        result: list[QueryHistoryEntry] = []

        for entry in self.history:
            entry.is_starred = entry.query.strip() in self.starred
            entry.is_starred_only = False
            history_queries.add(entry.query.strip())
            result.append(entry)

        # Add starred-only entries (queries that were starred but not in history)
        for starred_query in self.starred:
            if starred_query not in history_queries:
                # Create synthetic entry for starred-only query
                entry = QueryHistoryEntry(
                    query=starred_query,
                    timestamp="",  # No timestamp
                    connection_name=self.connection_name,
                    is_starred=True,
                    is_starred_only=True,
                )
                result.append(entry)

        # Sort: starred-only first, then starred-in-history, then regular history
        # All sorted by timestamp descending within their groups
        starred_only = [e for e in result if e.is_starred_only]
        starred_in_history = [e for e in result if e.is_starred and not e.is_starred_only]
        not_starred = [e for e in result if not e.is_starred]

        # Sort each group by timestamp descending
        starred_in_history.sort(key=lambda e: e.timestamp, reverse=True)
        not_starred.sort(key=lambda e: e.timestamp, reverse=True)

        return starred_only + starred_in_history + not_starred

    def compose(self) -> ComposeResult:
        title = f"Query History - {self.connection_name}"
        shortcuts = [("Select", "<enter>"), ("Star", "*"), ("Delete", "D"), ("Close", "<esc>")]

        self._merged_entries = self._merge_entries()

        with Dialog(id="history-dialog", title=title, shortcuts=shortcuts):
            with VerticalScroll(id="history-scroll"):
                if self._merged_entries:
                    options = []
                    for entry in self._merged_entries:
                        # Format timestamp
                        if entry.is_starred_only:
                            time_str = "Saved"
                        else:
                            try:
                                dt = datetime.fromisoformat(entry.timestamp)
                                time_str = dt.strftime("%Y-%m-%d %H:%M")
                            except (ValueError, AttributeError):
                                time_str = "Unknown"

                        # Star indicator
                        star = "[yellow]*[/] " if entry.is_starred else "  "

                        # Truncate query for display
                        query_preview = entry.query.replace("\n", " ")[:55]
                        if len(entry.query) > 55:
                            query_preview += "..."

                        # Use query hash for starred-only, timestamp for history entries
                        option_id = f"starred:{hash(entry.query)}" if entry.is_starred_only else entry.timestamp

                        options.append(Option(f"{star}[dim]{time_str}[/]  {query_preview}", id=option_id))

                    yield OptionList(*options, id="history-list")
                else:
                    yield Static("No query history for this connection", id="history-empty")

            with VerticalScroll(id="history-preview-container"):
                yield Static("", id="history-preview")

    def on_mount(self) -> None:
        if self._merged_entries:
            try:
                option_list = self.query_one("#history-list", OptionList)
                option_list.focus()
                self._update_preview(0)
            except Exception:
                pass

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id == "history-list":
            idx = event.option_list.highlighted
            if idx is not None:
                self._update_preview(idx)

    def _update_preview(self, idx: int) -> None:
        if idx < len(self._merged_entries):
            preview = self.query_one("#history-preview", Static)
            preview.update(self._merged_entries[idx].query)

    def action_select(self) -> None:
        if not self._merged_entries:
            self.dismiss(None)
            return

        try:
            option_list = self.query_one("#history-list", OptionList)
            idx = option_list.highlighted
            if idx is not None and idx < len(self._merged_entries):
                self.dismiss(("select", self._merged_entries[idx].query))
            else:
                self.dismiss(None)
        except Exception:
            self.dismiss(None)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "history-list":
            idx = event.option_list.highlighted
            if idx is not None and idx < len(self._merged_entries):
                self.dismiss(("select", self._merged_entries[idx].query))

    def action_delete(self) -> None:
        """Delete the selected history entry."""
        if not self._merged_entries:
            return

        try:
            option_list = self.query_one("#history-list", OptionList)
            idx = option_list.highlighted
            if idx is not None and idx < len(self._merged_entries):
                entry = self._merged_entries[idx]
                # For starred-only entries, there's nothing to delete from history
                if entry.is_starred_only:
                    return
                self.dismiss(("delete", entry.timestamp))
        except Exception:
            pass

    def action_toggle_star(self) -> None:
        """Toggle star status for the selected entry."""
        if not self._merged_entries:
            return

        try:
            option_list = self.query_one("#history-list", OptionList)
            idx = option_list.highlighted
            if idx is not None and idx < len(self._merged_entries):
                entry = self._merged_entries[idx]
                self.dismiss(("toggle_star", entry.query))
        except Exception:
            pass

    def action_cancel(self) -> None:
        self.dismiss(None)
