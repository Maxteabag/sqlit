"""Query history screen."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from textual.app import ComposeResult
from rich.text import Text
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from sqlit.domains.query.store.history import QueryHistoryEntry
from sqlit.shared.core.utils import fuzzy_match
from sqlit.shared.ui.widgets import Dialog, FilterInput


class QueryHistoryScreen(ModalScreen):
    """Modal screen for query history selection."""

    BINDINGS = [
        Binding("escape,q", "cancel", "Cancel", priority=True),
        Binding("enter", "select", "Select"),
        Binding("d", "delete", "Delete"),
        Binding("asterisk", "toggle_star", "Star"),
        Binding("slash", "open_filter", "Filter"),
        Binding("tab", "toggle_pane", "Pane", priority=True),
    ]

    CSS = """
    QueryHistoryScreen {
        align: center middle;
        background: transparent;
    }

    #history-dialog {
        width: 120;
        max-width: 95%;
        height: 24;
        min-height: 16;
        max-height: 80%;
    }

    #history-filter {
        background: $surface;
    }

    /* nvim-style split: list sidebar | preview window */
    #history-split {
        height: 1fr;
        width: 1fr;
    }

    #history-list-pane {
        width: 32;
        min-width: 24;
        max-width: 40%;
        height: 1fr;
        background: $surface;
        border: none;
        padding: 0;
    }

    #history-list-pane.active-pane {
        border-left: tall $primary;
    }

    #history-preview-pane {
        width: 1fr;
        height: 1fr;
        background: $surface-darken-1;
        border: none;
        padding: 1;
    }

    #history-preview-pane.active-pane {
        border-left: tall $primary;
    }

    #history-scroll {
        height: 1fr;
        background: $surface;
        border: none;
        padding: 0;
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
        height: 1fr;
        background: $surface-darken-1;
        border: none;
        padding: 0;
    }

    #history-preview {
        height: auto;
    }
    """

    def __init__(
        self,
        history: list,
        connection_name: str,
        starred: set[str] | None = None,
        *,
        multi_connection: bool = False,
        connection_labels: dict[str, str] | None = None,
        starred_by_connection: dict[str, set[str]] | None = None,
        auto_open_filter: bool = False,
    ):
        super().__init__()
        self.history = history  # list of QueryHistoryEntry
        self.connection_name = connection_name
        self.starred = starred or set()  # set of starred query strings
        self._multi_connection = multi_connection
        self._connection_labels = connection_labels or {}
        self._starred_by_connection = starred_by_connection or {}
        self._auto_open_filter = auto_open_filter
        self._merged_entries: list[QueryHistoryEntry] = []
        self._filter_active = False
        self._filter_text = ""
        self._filter_query = ""
        self._filter_fuzzy = False
        self._filtered_entries: list[QueryHistoryEntry] = []
        self._active_pane = "list"  # "list" or "preview"

    def _merge_entries(self) -> list[QueryHistoryEntry]:
        """Merge history entries with starred-only queries.

        Same-text rows collapse to a single most-recent entry so the row
        count matches the starring model (which is keyed by query text):
        starring one row never marks two visually-identical rows. In
        multi-connection (telescope) mode the dedupe key is
        (connection_name, query); in single-connection mode it's just
        the query.
        """
        result: list[QueryHistoryEntry] = []

        if self._multi_connection:
            seen: dict[tuple[str, str], QueryHistoryEntry] = {}
            for entry in self.history:
                starred_queries = self._starred_by_connection.get(entry.connection_name, set())
                entry.is_starred = entry.query.strip() in starred_queries
                entry.is_starred_only = False
                key = (entry.connection_name, entry.query.strip())
                existing = seen.get(key)
                if existing is None or entry.timestamp > existing.timestamp:
                    seen[key] = entry
            result.extend(seen.values())

            history_queries_by_connection: dict[str, set[str]] = {}
            for (conn_name, query_text) in seen:
                history_queries_by_connection.setdefault(conn_name, set()).add(query_text)

            for connection_name, starred_queries in self._starred_by_connection.items():
                history_queries = history_queries_by_connection.get(connection_name, set())
                for starred_query in starred_queries:
                    if starred_query not in history_queries:
                        entry = QueryHistoryEntry(
                            query=starred_query,
                            timestamp="",  # No timestamp
                            connection_name=connection_name,
                            is_starred=True,
                            is_starred_only=True,
                        )
                        result.append(entry)
        else:
            seen_single: dict[str, QueryHistoryEntry] = {}
            for entry in self.history:
                entry.is_starred = entry.query.strip() in self.starred
                entry.is_starred_only = False
                key = entry.query.strip()
                existing = seen_single.get(key)
                if existing is None or entry.timestamp > existing.timestamp:
                    seen_single[key] = entry
            result.extend(seen_single.values())

            history_queries = set(seen_single.keys())
            for starred_query in self.starred:
                if starred_query not in history_queries:
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
        if self._multi_connection:
            title = "Telescope - All Servers"
            empty_message = "No query history across servers"
        else:
            title = f"Query History - {self.connection_name}"
            empty_message = "No query history for this connection"
        shortcuts = [("Select", "<enter>"), ("Star", "*"), ("Delete", "D"), ("Pane", "<tab>")]

        self._merged_entries = self._merge_entries()

        with Dialog(id="history-dialog", title=title, shortcuts=shortcuts):
            yield FilterInput(id="history-filter")
            with Horizontal(id="history-split"):
                with Vertical(id="history-list-pane"):
                    with VerticalScroll(id="history-scroll"):
                        if self._merged_entries:
                            options = []
                            for entry in self._merged_entries:
                                options.append(self._build_option(entry))

                            yield OptionList(*options, id="history-list")
                        else:
                            yield Static(empty_message, id="history-empty")
                with Vertical(id="history-preview-pane"):
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
        self._set_active_pane("list")
        if self._auto_open_filter:
            self.action_open_filter()

    def action_toggle_pane(self) -> None:
        """Switch focus between the list pane and the preview pane (Tab).

        Works while a search filter is open so the user can jump to the
        preview to read a query without closing the filter.
        """
        self._set_active_pane("preview" if self._active_pane == "list" else "list")

    def _set_active_pane(self, pane: str) -> None:
        """Mark ``pane`` as active, update focus, and refresh pane borders."""
        self._active_pane = pane
        try:
            list_pane = self.query_one("#history-list-pane", Vertical)
            preview_pane = self.query_one("#history-preview-pane", Vertical)
        except Exception:
            return
        list_pane.set_class(pane == "list", "active-pane")
        preview_pane.set_class(pane == "preview", "active-pane")
        if pane == "list":
            try:
                self.query_one("#history-list", OptionList).focus()
            except Exception:
                pass
        else:
            try:
                self.query_one("#history-preview-container", VerticalScroll).focus()
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
            preview.update(Text(entries[idx].query))
            # Reset the preview scroll to the top so each query starts at
            # its first line instead of inheriting the previous query's
            # scroll offset.
            try:
                container = self.query_one("#history-preview-container", VerticalScroll)
                container.scroll_home(animate=False)
            except Exception:
                pass

    def action_select(self) -> None:
        entries = self._get_display_entries()
        if not entries:
            self.dismiss(None)
            return

        try:
            option_list = self.query_one("#history-list", OptionList)
            idx = option_list.highlighted
            if idx is not None and idx < len(entries):
                self.dismiss(self._build_action_result("select", entries[idx]))
            else:
                self.dismiss(None)
        except Exception:
            self.dismiss(None)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "history-list":
            idx = event.option_list.highlighted
            entries = self._get_display_entries()
            if idx is not None and idx < len(entries):
                self.dismiss(self._build_action_result("select", entries[idx]))

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
                self.dismiss(self._build_action_result("delete", entry))
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
                self.dismiss(self._build_action_result("toggle_star", entry))
        except Exception:
            pass

    def action_cancel(self) -> None:
        if self._filter_active:
            self._close_filter()
            return
        self.dismiss(None)

    def on_key(self, event: Any) -> None:
        # j/k always navigate the active pane, even while a filter is open:
        # in the preview pane they scroll the query; in the list pane they
        # move the highlight (no filter) or type into the filter (filter open).
        if event.key in ("j", "k") and self._active_pane == "preview":
            try:
                preview = self.query_one("#history-preview-container", VerticalScroll)
            except Exception:
                return
            if event.key == "j":
                preview.scroll_down()
            else:
                preview.scroll_up()
            event.prevent_default()
            event.stop()
            return

        if not self._filter_active:
            if event.key in ("j", "k"):
                try:
                    option_list = self.query_one("#history-list", OptionList)
                except Exception:
                    return
                if event.key == "j":
                    option_list.action_cursor_down()
                else:
                    option_list.action_cursor_up()
                event.prevent_default()
                event.stop()
            return

        # when in preview pane, disable filter modification
        if self._active_pane != "list":
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
        # in case of no history, no filter needed
        if not self._merged_entries:
            return

        # when in search mode, default pane is set to list
        if self._active_pane != "list":
            self._set_active_pane("list")

        # when some text is alredy in filter, `/` won't reset it
        if self._filter_active:
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
        if entry.is_starred_only or not entry.timestamp:
            suffix = f"starred:{hash(entry.query)}"
        else:
            suffix = entry.timestamp
        if self._multi_connection:
            return f"{entry.connection_name}:{suffix}"
        return suffix

    def _entry_connection_label(self, entry: QueryHistoryEntry) -> str:
        label = self._connection_labels.get(entry.connection_name, entry.connection_name)
        return label or entry.connection_name

    def _truncate_label(self, value: str, max_len: int) -> str:
        if len(value) > max_len:
            return value[: max_len - 3] + "..."
        return value

    def _build_action_result(self, action: str, entry: QueryHistoryEntry) -> tuple[str, Any]:
        if self._multi_connection:
            if action == "delete":
                payload = {"timestamp": entry.timestamp, "connection_name": entry.connection_name}
            else:
                payload: dict[str, str] = {"query": entry.query, "connection_name": entry.connection_name}
                if getattr(entry, "database", ""):
                    payload["database"] = entry.database
            return action, payload
        if action == "delete":
            return action, entry.timestamp
        return action, entry.query

    def _build_option(self, entry: QueryHistoryEntry) -> Option:
        # Build a Rich Text (not a markup string) so identifiers like
        # [dbo].[ServiceFeatures] aren't eaten by the markup parser:
        # rich.markup.escape only escapes "[a-z#/@…]" tags, so uppercase
        # bracket identifiers slip through and get consumed as fake tags.
        query_single_line = re.sub(r"\s+", " ", entry.query).strip()
        max_len = 40 if self._multi_connection else 55
        if len(query_single_line) > max_len:
            query_preview = query_single_line[:max_len] + "..."
        else:
            query_preview = query_single_line

        text = Text()
        if entry.is_starred:
            text.append("* ", style="yellow")
        else:
            text.append("  ")
        if self._multi_connection:
            conn_label = self._truncate_label(self._entry_connection_label(entry), 24)
            text.append(conn_label, style="dim")
            text.append("/")
        text.append(query_preview)
        return Option(text, id=self._entry_option_id(entry))
