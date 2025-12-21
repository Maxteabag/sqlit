"""Results filter mixin for SSMSTUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.markup import escape as escape_markup

from ...utils import fuzzy_match, highlight_matches
from ..protocols import AppProtocol

if TYPE_CHECKING:
    pass


class ResultsFilterMixin:
    """Mixin providing results table filter functionality.

    By default, uses fast case-insensitive substring matching.
    Prefix search with ~ for fuzzy matching (e.g., "~foo" for fuzzy search).
    """

    _results_filter_visible: bool = False
    _results_filter_text: str = ""
    _results_filter_matches: list[int] = []  # Row indices that match
    _results_filter_match_index: int = 0
    _results_filter_original_rows: list[tuple] = []  # Store original rows for restore
    _results_filter_matching_rows: list[tuple] = []  # Current filtered rows
    _results_filter_fuzzy: bool = False  # Whether fuzzy mode is active
    _results_filter_debounce_timer: Any = None  # Timer for debounced updates
    _results_filter_pending_update: bool = False  # Whether an update is pending

    # Maximum matches to display (performance optimization)
    MAX_FILTER_MATCHES = 5000

    @staticmethod
    def _get_debounce_ms(row_count: int) -> int:
        """Get debounce delay based on row count."""
        if row_count < 1000:
            return 0
        elif row_count < 10000:
            return 50
        elif row_count < 50000:
            return 100
        elif row_count < 100000:
            return 150
        else:
            return 200

    def action_results_filter(self: AppProtocol) -> None:
        """Open the results filter."""
        if not self.results_table.has_focus:
            self.results_table.focus()

        # Check if there are results to filter
        if not self._last_result_rows:
            self.notify("No results to filter", severity="warning")
            return

        self._results_filter_visible = True
        self._results_filter_text = ""
        self._results_filter_matches = []
        self._results_filter_match_index = 0
        # Store original rows for restoration
        self._results_filter_original_rows = list(self._last_result_rows)
        # Initially all rows match (no filter applied)
        self._results_filter_matching_rows = list(self._last_result_rows)

        self.results_filter_input.show()
        # Just update the filter display, table already has the data
        total = len(self._results_filter_original_rows)
        self.results_filter_input.set_filter("", 0, total)
        self._update_footer_bindings()

    def action_results_filter_close(self: AppProtocol) -> None:
        """Close the results filter and restore original data."""
        self._results_filter_visible = False
        self._results_filter_text = ""
        self.results_filter_input.hide()

        # Restore original data
        if self._results_filter_original_rows:
            self._replace_results_table(self._last_result_columns, self._results_filter_original_rows)  # type: ignore[attr-defined]
            self._last_result_rows = list(self._results_filter_original_rows)

        self._update_footer_bindings()

    def action_results_filter_accept(self: AppProtocol) -> None:
        """Accept current filter selection and close, keeping filtered view."""
        self._results_filter_visible = False
        self._results_filter_text = ""
        self.results_filter_input.hide()

        # Update stored rows to the filtered data
        self._last_result_rows = list(self._results_filter_matching_rows)

        self._update_footer_bindings()

    def action_results_filter_next(self: AppProtocol) -> None:
        """Move to next filter match."""
        if not self._results_filter_matches:
            return
        self._results_filter_match_index = (self._results_filter_match_index + 1) % len(
            self._results_filter_matches
        )
        self._jump_to_current_results_match()

    def action_results_filter_prev(self: AppProtocol) -> None:
        """Move to previous filter match."""
        if not self._results_filter_matches:
            return
        self._results_filter_match_index = (self._results_filter_match_index - 1) % len(
            self._results_filter_matches
        )
        self._jump_to_current_results_match()

    def _jump_to_current_results_match(self: AppProtocol) -> None:
        """Jump to the current match in the results table."""
        if not self._results_filter_matches:
            return
        table = self.results_table
        # The match index corresponds to row in the filtered table
        row_idx = self._results_filter_match_index
        if row_idx < table.row_count:
            table.move_cursor(row=row_idx, column=0)

    def on_key(self: AppProtocol, event: Any) -> None:
        """Handle key events when results filter is active."""
        if not self._results_filter_visible:
            # Pass to next mixin in chain if it has on_key
            parent = super()
            if hasattr(parent, "on_key"):
                parent.on_key(event)  # type: ignore[misc]
            return

        key = event.key

        # Close filter and restore original data
        if key == "escape":
            self.action_results_filter_close()
            event.prevent_default()
            event.stop()
            return

        # Accept filter and keep filtered data
        if key == "enter":
            self.action_results_filter_accept()
            event.prevent_default()
            event.stop()
            return

        # Handle backspace
        if key == "backspace":
            if self._results_filter_text:
                self._results_filter_text = self._results_filter_text[:-1]
                self._schedule_filter_update()
            else:
                # Exit filter when backspacing with no text
                self.action_results_filter_close()
            event.prevent_default()
            event.stop()
            return

        # Handle printable characters - use event.character for proper shift support
        char = getattr(event, "character", None)
        if char and char.isprintable():
            self._results_filter_text += char
            self._schedule_filter_update()
            event.prevent_default()
            event.stop()
            return

        # For other keys, pass to parent
        parent = super()
        if hasattr(parent, "on_key"):
            parent.on_key(event)  # type: ignore[misc]

    def _schedule_filter_update(self: AppProtocol) -> None:
        """Schedule a debounced filter update based on row count."""
        # Cancel any pending timer
        if self._results_filter_debounce_timer:
            self._results_filter_debounce_timer.stop()
            self._results_filter_debounce_timer = None

        # Update filter input immediately to show what user typed
        total = len(self._results_filter_original_rows)
        self.results_filter_input.set_filter(
            self._results_filter_text,
            len(self._results_filter_matches) if self._results_filter_matches else 0,
            total,
        )

        # Get debounce delay based on row count
        debounce_ms = self._get_debounce_ms(total)

        if debounce_ms == 0:
            # No debounce needed, update immediately
            self._update_results_filter()
        else:
            # Schedule debounced update
            self._results_filter_pending_update = True
            self._results_filter_debounce_timer = self.set_timer(
                debounce_ms / 1000.0,
                self._do_debounced_filter_update,
            )

    def _do_debounced_filter_update(self: AppProtocol) -> None:
        """Execute the debounced filter update."""
        self._results_filter_debounce_timer = None
        if self._results_filter_pending_update:
            self._results_filter_pending_update = False
            self._update_results_filter()

    def _update_results_filter(self: AppProtocol) -> None:
        """Update the results table based on current filter text.

        Uses simple case-insensitive substring matching by default.
        Prefix with ~ for fuzzy matching.
        """
        total = len(self._results_filter_original_rows)

        if not self._results_filter_text:
            # Restore all rows
            self._restore_results_table()
            self._results_filter_matches = []
            self._results_filter_matching_rows = list(self._results_filter_original_rows)
            self._results_filter_fuzzy = False
            self.results_filter_input.set_filter("", 0, total)
            return

        # Check for fuzzy mode prefix
        search_text = self._results_filter_text
        if search_text.startswith("~"):
            self._results_filter_fuzzy = True
            search_text = search_text[1:]  # Remove prefix
            if not search_text:
                # Just "~" entered, show all rows
                self._restore_results_table()
                self._results_filter_matches = []
                self._results_filter_matching_rows = list(self._results_filter_original_rows)
                self.results_filter_input.set_filter("~", 0, total)
                return
        else:
            self._results_filter_fuzzy = False

        # Find matching rows (with early exit for performance)
        matches: list[int] = []
        matching_rows: list[tuple] = []
        search_lower = search_text.lower()
        hit_limit = False

        for row_idx, row in enumerate(self._results_filter_original_rows):
            row_text = " ".join(str(cell) if cell is not None else "" for cell in row)

            if self._results_filter_fuzzy:
                matched, _ = fuzzy_match(search_text, row_text)
            else:
                # Fast case-insensitive substring match
                matched = search_lower in row_text.lower()

            if matched:
                matches.append(row_idx)
                matching_rows.append(row)

                # Early exit if we've found enough matches
                if len(matches) >= self.MAX_FILTER_MATCHES:
                    hit_limit = True
                    break

        self._results_filter_matches = matches
        self._results_filter_match_index = 0
        self._results_filter_matching_rows = matching_rows

        # Rebuild table with only matching rows
        self._rebuild_results_with_matches(matching_rows, search_text)

        # Update filter display (show "5000+" if we hit the limit)
        match_count = len(matches)
        if hit_limit:
            # Signal that there are more matches
            self.results_filter_input.set_filter(
                self._results_filter_text, match_count, total, truncated=True
            )
        else:
            self.results_filter_input.set_filter(
                self._results_filter_text, match_count, total
            )

        # Jump to first match
        if matches:
            self._jump_to_current_results_match()

    def _rebuild_results_with_matches(self: AppProtocol, matching_rows: list[tuple], search_text: str) -> None:
        """Rebuild the results table with only matching rows."""
        # Build highlighted rows
        highlighted_rows: list[tuple] = []
        search_lower = search_text.lower()

        for row in matching_rows:
            highlighted_row = []
            for cell in row:
                cell_str = str(cell) if cell is not None else "NULL"
                if search_text:
                    if self._results_filter_fuzzy:
                        # Fuzzy highlighting
                        matched, indices = fuzzy_match(search_text, cell_str)
                        if matched:
                            cell_str = highlight_matches(
                                escape_markup(cell_str), indices, style="bold #FFFF00"
                            )
                        else:
                            cell_str = escape_markup(cell_str)
                    else:
                        # Simple substring highlighting
                        cell_str = self._highlight_substring(cell_str, search_lower)
                else:
                    cell_str = escape_markup(cell_str)
                highlighted_row.append(cell_str)
            highlighted_rows.append(tuple(highlighted_row))

        # Update the table with filtered results (markup already applied)
        self._replace_results_table_raw(self._last_result_columns, highlighted_rows)  # type: ignore[attr-defined]

    def _highlight_substring(self: AppProtocol, text: str, search_lower: str) -> str:
        """Highlight substring matches in text (case-insensitive)."""
        text_lower = text.lower()
        start = text_lower.find(search_lower)
        if start == -1:
            return escape_markup(text)

        # Find all non-overlapping matches and highlight them
        result_parts = []
        pos = 0
        while start != -1:
            # Add text before match
            if start > pos:
                result_parts.append(escape_markup(text[pos:start]))
            # Add highlighted match
            end = start + len(search_lower)
            result_parts.append(f"[bold #FFFF00]{escape_markup(text[start:end])}[/]")
            pos = end
            start = text_lower.find(search_lower, pos)

        # Add remaining text
        if pos < len(text):
            result_parts.append(escape_markup(text[pos:]))

        return "".join(result_parts)

    def _restore_results_table(self: AppProtocol) -> None:
        """Restore the results table to show all original rows."""
        if not self._results_filter_original_rows:
            return

        # Use _replace_results_table which handles escaping
        self._replace_results_table(self._last_result_columns, self._results_filter_original_rows)  # type: ignore[attr-defined]

        # Update stored rows to match original
        self._last_result_rows = list(self._results_filter_original_rows)
