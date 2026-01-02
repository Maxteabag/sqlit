"""Result rendering helpers for query execution."""

from __future__ import annotations

from typing import Any

import pyarrow as pa
from rich.markup import escape as escape_markup
from textual_fastdatatable import ArrowBackend

from sqlit.shared.core.utils import format_duration_ms
from sqlit.shared.ui.protocols import QueryMixinHost
from sqlit.shared.ui.widgets import SqlitDataTable

from .query_constants import MAX_COLUMN_CONTENT_WIDTH, MAX_RENDER_ROWS


class QueryResultsMixin:
    """Mixin providing results rendering for queries."""

    def _replace_results_table(self: QueryMixinHost, columns: list[str], rows: list[tuple]) -> None:
        """Update the results table with escaped data."""
        self._replace_results_table_with_data(columns, rows, escape=True)

    def _replace_results_table_raw(self: QueryMixinHost, columns: list[str], rows: list[tuple]) -> None:
        """Update the results table with pre-formatted data (no escaping)."""
        self._replace_results_table_with_data(columns, rows, escape=False)
    def _replace_results_table_with_data(
        self: QueryMixinHost,
        columns: list[str],
        rows: list[tuple],
        *,
        escape: bool,
    ) -> None:
        """Replace the results table with new data."""
        container = self.results_area
        old_table = self.results_table
        new_table = self._build_results_table(columns, rows, escape=escape)
        container.mount(new_table, after=old_table)
        old_table.remove()

    def _build_results_table(
        self: QueryMixinHost,
        columns: list[str],
        rows: list[tuple],
        *,
        escape: bool,
    ) -> SqlitDataTable:
        """Build a new results table with optional markup escaping."""
        self._results_table_counter += 1
        new_id = f"results-table-{self._results_table_counter}"

        if not columns:
            return SqlitDataTable(id=new_id, zebra_stripes=True, show_header=False)

        if not rows:
            empty_columns: dict[str, list[Any]] = {col: [] for col in columns}
            arrow_table = pa.table(empty_columns)
            backend = ArrowBackend(arrow_table)
            return SqlitDataTable(
                id=new_id,
                zebra_stripes=True,
                backend=backend,
                max_column_content_width=MAX_COLUMN_CONTENT_WIDTH,
            )

        if escape:
            formatted_rows = []
            for row in rows[:MAX_RENDER_ROWS]:
                formatted = []
                for i in range(len(columns)):
                    val = row[i] if i < len(row) else None
                    str_val = escape_markup(str(val)) if val is not None else "NULL"
                    formatted.append(str_val)
                formatted_rows.append(formatted)

            formatted_columns: dict[str, list[Any]] = {
                col: [r[i] for r in formatted_rows] for i, col in enumerate(columns)
            }
            arrow_table = pa.table(formatted_columns)
        else:
            raw_columns: dict[str, list[Any]] = {}
            for i, col in enumerate(columns):
                raw_columns[col] = [r[i] for r in rows[:MAX_RENDER_ROWS]]
            arrow_table = pa.table(raw_columns)

        backend = ArrowBackend(arrow_table)
        return SqlitDataTable(
            id=new_id,
            zebra_stripes=True,
            backend=backend,
            max_column_content_width=MAX_COLUMN_CONTENT_WIDTH,
        )

    def _display_query_results(
        self: QueryMixinHost, columns: list[str], rows: list[tuple], row_count: int, truncated: bool, elapsed_ms: float
    ) -> None:
        """Display query results in the results table (called on main thread)."""
        self._last_result_columns = columns
        self._last_result_rows = rows
        self._last_result_row_count = row_count

        # Switch to single result mode (in case we were showing stacked results)
        self._show_single_result_mode()

        self._replace_results_table(columns, rows)

        time_str = format_duration_ms(elapsed_ms)
        if truncated:
            self.notify(
                f"Query returned {row_count}+ rows in {time_str} (truncated)",
                severity="warning",
            )
        else:
            self.notify(f"Query returned {row_count} rows in {time_str}")

    def _display_non_query_result(self: QueryMixinHost, affected: int, elapsed_ms: float) -> None:
        """Display non-query result (called on main thread)."""
        self._last_result_columns = ["Result"]
        self._last_result_rows = [(f"{affected} row(s) affected",)]
        self._last_result_row_count = 1

        # Switch to single result mode (in case we were showing stacked results)
        self._show_single_result_mode()

        self._replace_results_table(["Result"], [(f"{affected} row(s) affected",)])
        time_str = format_duration_ms(elapsed_ms)
        self.notify(f"Query executed: {affected} row(s) affected in {time_str}")

    def _display_query_error(self: QueryMixinHost, error_message: str) -> None:
        """Display query error (called on main thread)."""
        # notify(severity="error") handles displaying the error in results via _show_error_in_results
        self.notify(f"Query error: {error_message}", severity="error")

    def _display_multi_statement_results(
        self: QueryMixinHost,
        multi_result: Any,
        elapsed_ms: float,
    ) -> None:
        """Display stacked results for multi-statement query."""
        from sqlit.shared.ui.widgets_stacked_results import (
            AUTO_COLLAPSE_THRESHOLD,
        )

        # Get or create stacked results container
        container = self._get_stacked_results_container()
        container.clear_results()

        # Determine if we should auto-collapse
        auto_collapse = len(multi_result.results) > AUTO_COLLAPSE_THRESHOLD

        # Add each result section
        for i, stmt_result in enumerate(multi_result.results):
            container.add_result_section(stmt_result, i, auto_collapse=auto_collapse)

        # Show the stacked results container, hide single result table
        self._show_stacked_results_mode()

        # Update notification
        time_str = format_duration_ms(elapsed_ms)
        success_count = multi_result.successful_count
        total = len(multi_result.results)

        if multi_result.has_error:
            error_idx = multi_result.error_index + 1
            self.notify(
                f"Executed {success_count}/{total} statements in {time_str} (error at #{error_idx})",
                severity="error",
            )
        else:
            self.notify(f"Executed {total} statements in {time_str}")

    def _get_stacked_results_container(self: QueryMixinHost) -> Any:
        """Get the stacked results container."""
        from textual.css.query import NoMatches

        from sqlit.shared.ui.widgets_stacked_results import StackedResultsContainer

        try:
            return self.query_one("#stacked-results", StackedResultsContainer)
        except NoMatches:
            # Container should exist in layout, but create if missing
            container = StackedResultsContainer(id="stacked-results")
            self.results_area.mount(container)
            return container

    def _show_stacked_results_mode(self: QueryMixinHost) -> None:
        """Switch to stacked results mode (hide single table, show stacked container)."""
        self.results_area.add_class("stacked-mode")
        try:
            stacked = self.query_one("#stacked-results")
            stacked.add_class("active")
        except Exception:
            pass

    def _show_single_result_mode(self: QueryMixinHost) -> None:
        """Switch to single result mode (show single table, hide stacked container)."""
        self.results_area.remove_class("stacked-mode")
        try:
            stacked = self.query_one("#stacked-results")
            stacked.remove_class("active")
        except Exception:
            pass
