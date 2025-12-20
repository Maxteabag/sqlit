"""Results filter mixin for SSMSTUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.markup import escape as escape_markup

from ...utils import fuzzy_match, highlight_matches
from ..protocols import AppProtocol

if TYPE_CHECKING:
    pass


class ResultsFilterMixin:
    """Mixin providing results table filter functionality."""

    _results_filter_visible: bool = False
    _results_filter_text: str = ""
    _results_filter_matches: list[int] = []  # Row indices that match
    _results_filter_match_index: int = 0
    _results_filter_original_rows: list[tuple] = []  # Store original rows for restore

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

        self.results_filter_input.show()
        self._update_results_filter()
        self._update_footer_bindings()

    def action_results_filter_close(self: AppProtocol) -> None:
        """Close the results filter and restore table."""
        self._results_filter_visible = False
        self._results_filter_text = ""
        self.results_filter_input.hide()
        self._restore_results_table()
        self._update_footer_bindings()

    def action_results_filter_accept(self: AppProtocol) -> None:
        """Accept current filter selection and close."""
        # Keep the filtered view, just close the filter UI
        self._results_filter_visible = False
        self._results_filter_text = ""
        self.results_filter_input.hide()
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
        # The match index corresponds to row in the filtered table
        row_idx = self._results_filter_match_index
        if row_idx < self.results_table.row_count:
            self.results_table.move_cursor(row=row_idx, column=0)

    def on_key(self: AppProtocol, event: Any) -> None:
        """Handle key events when results filter is active."""
        if not self._results_filter_visible:
            # Pass to next mixin in chain if it has on_key
            parent = super()
            if hasattr(parent, "on_key"):
                parent.on_key(event)  # type: ignore[misc]
            return

        key = event.key

        # Handle backspace
        if key == "backspace":
            if self._results_filter_text:
                self._results_filter_text = self._results_filter_text[:-1]
                self._update_results_filter()
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
            self._update_results_filter()
            event.prevent_default()
            event.stop()
            return

        # Don't need to chain further - we're near end of MRO

    def _update_results_filter(self: AppProtocol) -> None:
        """Update the results table based on current filter text."""
        total = len(self._results_filter_original_rows)

        if not self._results_filter_text:
            # Restore all rows
            self._restore_results_table()
            self._results_filter_matches = []
            self.results_filter_input.set_filter("", 0, total)
            return

        # Find matching rows
        matches: list[int] = []
        matching_rows: list[tuple] = []

        for row_idx, row in enumerate(self._results_filter_original_rows):
            row_text = " ".join(str(cell) if cell is not None else "" for cell in row)
            matched, _ = fuzzy_match(self._results_filter_text, row_text)
            if matched:
                matches.append(row_idx)
                matching_rows.append(row)

        self._results_filter_matches = matches
        self._results_filter_match_index = 0

        # Rebuild table with only matching rows
        self._rebuild_results_with_matches(matching_rows)

        # Update filter display
        self.results_filter_input.set_filter(
            self._results_filter_text, len(matches), total
        )

        # Jump to first match
        if matches:
            self._jump_to_current_results_match()

    def _rebuild_results_with_matches(self: AppProtocol, matching_rows: list[tuple]) -> None:
        """Rebuild the results table with only matching rows."""
        table = self.results_table

        # Clear and rebuild with same columns
        table.clear()

        for row in matching_rows:
            # Highlight matching text in cells
            highlighted_row = []
            for cell in row:
                cell_str = str(cell) if cell is not None else "NULL"
                if self._results_filter_text:
                    matched, indices = fuzzy_match(self._results_filter_text, cell_str)
                    if matched:
                        cell_str = highlight_matches(
                            escape_markup(cell_str), indices, style="bold #FFFF00"
                        )
                    else:
                        cell_str = escape_markup(cell_str)
                else:
                    cell_str = escape_markup(cell_str)
                highlighted_row.append(cell_str)
            table.add_row(*highlighted_row)

    def _restore_results_table(self: AppProtocol) -> None:
        """Restore the results table to show all original rows."""
        if not self._results_filter_original_rows:
            return

        table = self.results_table
        table.clear()

        for row in self._results_filter_original_rows:
            display_row = [
                escape_markup(str(cell)) if cell is not None else "NULL"
                for cell in row
            ]
            table.add_row(*display_row)

        # Update stored rows to match original
        self._last_result_rows = list(self._results_filter_original_rows)
