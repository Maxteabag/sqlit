"""Query history screen."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from sqlit.domains.query.store.history import QueryHistoryEntry
from sqlit.shared.core.utils import fuzzy_match
from sqlit.shared.ui.widgets import Dialog, FilterInput


class QueryHistoryScreen(ModalScreen):
    """Modal screen for query history selection."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("q", "cancel", "Cancel"),
        Binding("enter", "select", "Select"),
        Binding("d", "delete", "Delete"),
        Binding("asterisk", "toggle_star", "Star"),
        Binding("slash", "open_filter", "Filter"),
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

    #history-filter {
        background: $surface;
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
        self._filter_active = False
        self._filter_text = ""
        self._filter_query = ""
        self._filter_fuzzy = False
        self._filtered_entries: list[QueryHistoryEntry] = []

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
        shortcuts = [("Select", "<enter>"), ("Star", "*"), ("Delete", "D")]

        self._merged_entries = self._merge_entries()

        with Dialog(id="history-dialog", title=title, shortcuts=shortcuts):
            yield FilterInput(id="history-filter")
            with VerticalScroll(id="history-scroll"):
                if self._merged_entries:
                    options = []
                    for entry in self._merged_entries:
                        options.append(self._build_option(entry))

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
        try:
            filter_input = self.query_one("#history-filter", FilterInput)
            filter_input.hide()
        except Exception:
            pass

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id == "history-list":
            idx = event.option_list.highlighted
            if idx is not None:
                self._update_preview(idx)

    def _update_preview(self, idx: int) -> None:
        entries = self._get_display_entries()
        if idx < len(entries):
            preview = self.query_one("#history-preview", Static)
            preview.update(entries[idx].query)

    def action_select(self) -> None:
        entries = self._get_display_entries()
        if not entries:
            self.dismiss(None)
            return

        try:
            option_list = self.query_one("#history-list", OptionList)
            idx = option_list.highlighted
            if idx is not None and idx < len(entries):
                self.dismiss(("select", entries[idx].query))
            else:
                self.dismiss(None)
        except Exception:
            self.dismiss(None)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "history-list":
            idx = event.option_list.highlighted
            entries = self._get_display_entries()
            if idx is not None and idx < len(entries):
                self.dismiss(("select", entries[idx].query))

    def action_delete(self) -> None:
        """Delete the selected history entry."""
        entries = self._get_display_entries()
        if not entries:
            return

        try:
            option_list = self.query_one("#history-list", OptionList)
            idx = option_list.highlighted
            if idx is not None and idx < len(entries):
                entry = entries[idx]
                # For starred-only entries, there's nothing to delete from history
                if entry.is_starred_only:
                    return
                self.dismiss(("delete", entry.timestamp))
        except Exception:
            pass

    def action_toggle_star(self) -> None:
        """Toggle star status for the selected entry."""
        entries = self._get_display_entries()
        if not entries:
            return

        try:
            option_list = self.query_one("#history-list", OptionList)
            idx = option_list.highlighted
            if idx is not None and idx < len(entries):
                entry = entries[idx]
                self.dismiss(("toggle_star", entry.query))
        except Exception:
            pass

    def action_cancel(self) -> None:
        if self._filter_active:
            self._close_filter()
            return
        self.dismiss(None)

    def on_key(self, event: Any) -> None:
        if not self._filter_active:
            return

        key = event.key
        if key == "backspace":
            if self._filter_text:
                self._filter_text = self._filter_text[:-1]
                self._apply_filter()
            else:
                self._close_filter()
            event.prevent_default()
            event.stop()
            return

        if event.character and event.character.isprintable():
            if event.character == "/":
                event.prevent_default()
                event.stop()
                return
            self._filter_text += event.character
            self._apply_filter()
            event.prevent_default()
            event.stop()

    def action_open_filter(self) -> None:
        if not self._merged_entries:
            return
        self._filter_active = True
        self._filter_text = ""
        self._filter_query = ""
        self._filter_fuzzy = False
        try:
            filter_input = self.query_one("#history-filter", FilterInput)
            filter_input.show()
        except Exception:
            pass
        self._apply_filter()

    def _close_filter(self) -> None:
        self._filter_active = False
        self._filter_text = ""
        self._filter_query = ""
        self._filter_fuzzy = False
        self._filtered_entries = []
        try:
            filter_input = self.query_one("#history-filter", FilterInput)
            filter_input.hide()
        except Exception:
            pass
        self._rebuild_list()

    def _apply_filter(self) -> None:
        self._filter_fuzzy = self._filter_text.startswith("~")
        self._filter_query = self._filter_text[1:] if self._filter_fuzzy else self._filter_text

        if not self._filter_query:
            self._filtered_entries = []
        else:
            self._filtered_entries = [
                entry for entry in self._merged_entries if self._entry_matches(entry)
            ]
        self._update_filter_display()
        self._rebuild_list()

    def _entry_matches(self, entry: QueryHistoryEntry) -> bool:
        query = entry.query or ""
        if self._filter_fuzzy:
            matched, _ = fuzzy_match(self._filter_query, query)
            return matched
        return self._filter_query.lower() in query.lower()

    def _get_display_entries(self) -> list[QueryHistoryEntry]:
        if self._filter_query:
            return self._filtered_entries
        return self._merged_entries

    def _update_filter_display(self) -> None:
        try:
            filter_input = self.query_one("#history-filter", FilterInput)
        except Exception:
            return
        total = len(self._merged_entries)
        if self._filter_text:
            filter_input.set_filter(self._filter_text, len(self._get_display_entries()), total)
        else:
            filter_input.set_filter("", 0, total)

    def _rebuild_list(self) -> None:
        try:
            option_list = self.query_one("#history-list", OptionList)
        except Exception:
            return

        previous_id = None
        if option_list.highlighted is not None:
            try:
                prev_option = option_list.get_option_at_index(option_list.highlighted)
                if prev_option:
                    previous_id = prev_option.id
            except Exception:
                pass

        option_list.clear_options()
        for entry in self._get_display_entries():
            option_list.add_option(self._build_option(entry))

        self._restore_selection(previous_id)
        self._update_preview_for_selection()

    def _restore_selection(self, previous_id: str | None) -> None:
        try:
            option_list = self.query_one("#history-list", OptionList)
        except Exception:
            return

        if previous_id:
            for i in range(option_list.option_count):
                option = option_list.get_option_at_index(i)
                if option and option.id == previous_id and not option.disabled:
                    option_list.highlighted = i
                    return

        if option_list.option_count:
            option_list.highlighted = 0

    def _update_preview_for_selection(self) -> None:
        try:
            option_list = self.query_one("#history-list", OptionList)
        except Exception:
            return

        if option_list.highlighted is None:
            try:
                preview = self.query_one("#history-preview", Static)
                preview.update("")
            except Exception:
                pass
            return

        self._update_preview(option_list.highlighted)

    def _entry_time_label(self, entry: QueryHistoryEntry) -> str:
        if entry.is_starred_only:
            return "Saved"
        try:
            dt = datetime.fromisoformat(entry.timestamp)
            return dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, AttributeError):
            return "Unknown"

    def _entry_option_id(self, entry: QueryHistoryEntry) -> str:
        return f"starred:{hash(entry.query)}" if entry.is_starred_only else entry.timestamp

    def _build_option(self, entry: QueryHistoryEntry) -> Option:
        time_str = self._entry_time_label(entry)
        star = "[yellow]*[/] " if entry.is_starred else "  "
        # Collapse all whitespace to single spaces and strip
        query_single_line = re.sub(r"\s+", " ", entry.query).strip()
        max_len = 55
        if len(query_single_line) > max_len:
            query_preview = query_single_line[:max_len] + "..."
        else:
            query_preview = query_single_line
        option_id = self._entry_option_id(entry)
        return Option(f"{star}[dim]{time_str}[/]  {query_preview}", id=option_id)
