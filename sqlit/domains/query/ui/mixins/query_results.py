"""Result rendering helpers for query execution."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlit.shared.core.utils import format_duration_ms
from sqlit.shared.ui.protocols import QueryMixinHost
from sqlit.shared.ui.widgets import SqlitDataTable

from .query_constants import MAX_COLUMN_CONTENT_WIDTH, MAX_RENDER_ROWS

RESULTS_RENDER_CHUNK_SIZE = 200
RESULTS_RENDER_INITIAL_ROWS = 20


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
        self._cancel_results_render()
        container = self.results_area
        old_table = self.results_table
        was_focused = old_table.has_focus
        new_table = self._build_results_table(columns, rows, escape=escape)
        container.mount(new_table, after=old_table)
        old_table.remove()
        if was_focused:
            new_table.focus()

    def _build_results_table(
        self: QueryMixinHost,
        columns: list[str],
        rows: list[tuple],
        *,
        escape: bool,
        backend: Any | None = None,
    ) -> SqlitDataTable:
        """Build a new results table without converting to Arrow."""
        self._results_table_counter += 1
        new_id = f"results-table-{self._results_table_counter}"

        if not columns:
            return SqlitDataTable(id=new_id, zebra_stripes=True, show_header=False)

        render_markup = not escape
        if backend is not None:
            return SqlitDataTable(
                id=new_id,
                zebra_stripes=True,
                backend=backend,
                column_labels=columns,
                max_column_content_width=MAX_COLUMN_CONTENT_WIDTH,
                render_markup=render_markup,
                null_rep="NULL",
            )

        render_rows = rows[:MAX_RENDER_ROWS] if rows else []
        return SqlitDataTable(
            id=new_id,
            zebra_stripes=True,
            data=render_rows,
            column_labels=columns,
            max_column_content_width=MAX_COLUMN_CONTENT_WIDTH,
            render_markup=render_markup,
            null_rep="NULL",
        )

    def _get_decimal_column_types(self: QueryMixinHost, rows: list[tuple]) -> dict[int, Any]:
        from decimal import Decimal

        max_precision: dict[int, int] = {}
        max_scale: dict[int, int] = {}

        for row in rows:
            for idx, value in enumerate(row):
                if isinstance(value, Decimal):
                    digits = len(value.as_tuple().digits)
                    exponent = value.as_tuple().exponent
                    scale = -exponent if exponent < 0 else 0
                    precision = digits + (exponent if exponent > 0 else 0)
                    if precision < 1:
                        precision = 1
                    max_precision[idx] = max(max_precision.get(idx, 0), precision)
                    max_scale[idx] = max(max_scale.get(idx, 0), scale)

        if not max_precision:
            return {}

        import pyarrow as pa

        types: dict[int, Any] = {}
        for idx, precision in max_precision.items():
            scale = max_scale.get(idx, 0)
            if precision < scale:
                precision = scale
            if precision > 38:
                types[idx] = pa.decimal256(precision, scale)
            else:
                types[idx] = pa.decimal128(precision, scale)

        return types

    def _replace_results_table_with_table(self: QueryMixinHost, table: SqlitDataTable) -> None:
        """Replace the results table with a prebuilt table."""
        container = self.results_area
        old_table = self.results_table
        was_focused = old_table.has_focus
        container.mount(table, after=old_table)
        old_table.remove()
        if was_focused:
            table.focus()

    def _cancel_results_render(self: QueryMixinHost) -> None:
        """Cancel any in-flight results rendering worker."""
        worker = getattr(self, "_results_render_worker", None)
        if worker is not None:
            worker.cancel()
            self._results_render_worker = None
        token = getattr(self, "_results_render_token", 0)
        self._results_render_token = token + 1
        try:
            from sqlit.domains.shell.app.idle_scheduler import get_idle_scheduler
        except Exception:
            scheduler = None
        else:
            scheduler = get_idle_scheduler()
        if scheduler:
            scheduler.cancel_all(name="results-render")

    def _schedule_results_render(
        self: QueryMixinHost,
        table: SqlitDataTable,
        columns: list[str],
        rows: list[tuple],
        *,
        escape: bool,
        coerce_to_str_columns: set[int] | None = None,
        start_index: int,
        row_limit: int,
        render_token: int,
    ) -> None:
        if not rows or row_limit <= 0:
            return

        index = max(0, start_index)
        total = min(len(rows), row_limit)
        if index >= total:
            return

        def add_batch() -> None:
            nonlocal index
            if render_token != getattr(self, "_results_render_token", 0):
                return
            end = min(index + RESULTS_RENDER_CHUNK_SIZE, total)
            if end <= index:
                return
            batch = rows[index:end]
            if coerce_to_str_columns:
                coerced: list[tuple] = []
                for row in batch:
                    new_row = []
                    for col_idx, value in enumerate(row):
                        if col_idx in coerce_to_str_columns and value is not None:
                            new_row.append(str(value))
                        else:
                            new_row.append(value)
                    coerced.append(tuple(new_row))
                batch = coerced
            try:
                table.add_rows(batch)
            except Exception as exc:
                # Fall back to full render if incremental append fails (e.g., Arrow schema mismatch).
                try:
                    self.log.error(f"Results incremental render failed; falling back to full render: {exc}")
                except Exception:
                    pass
                if render_token == getattr(self, "_results_render_token", 0):
                    self._replace_results_table_with_data(columns, rows, escape=escape)
                return
            index = end
            if index < total:
                schedule_next()

        def schedule_next() -> None:
            try:
                from sqlit.domains.shell.app.idle_scheduler import Priority, get_idle_scheduler
            except Exception:
                scheduler = None
            else:
                scheduler = get_idle_scheduler()
            if scheduler:
                scheduler.request_idle_callback(
                    add_batch,
                    priority=Priority.NORMAL,
                    name="results-render",
                )
            else:
                self.set_timer(0.001, add_batch)

        schedule_next()

    def _render_results_table_incremental(
        self: QueryMixinHost,
        columns: list[str],
        rows: list[tuple],
        *,
        escape: bool,
        row_limit: int,
        render_token: int,
        table_info: dict[str, Any] | None = None,
    ) -> None:
        initial_count = min(RESULTS_RENDER_INITIAL_ROWS, row_limit)
        initial_rows = rows[:initial_count] if initial_count > 0 else []
        has_decimal_in_initial = any(
            isinstance(value, Decimal) for row in initial_rows for value in row
        )
        coerce_to_str_columns: set[int] | None = None
        try:
            if has_decimal_in_initial:
                decimal_types = self._get_decimal_column_types(rows)
                if decimal_types:
                    from textual_fastdatatable.backend import ArrowBackend
                    import pyarrow as pa

                    arrays = []
                    coerce_to_str_columns = set()
                    for idx, _name in enumerate(columns):
                        values = [row[idx] for row in initial_rows] if initial_rows else []
                        col_type = decimal_types.get(idx)
                        try:
                            if col_type is not None:
                                arrays.append(pa.array(values, type=col_type))
                            else:
                                arrays.append(pa.array(values))
                        except (TypeError, ValueError, pa.ArrowInvalid, pa.ArrowTypeError):
                            coerce_to_str_columns.add(idx)
                            arrays.append(
                                pa.array(
                                    [str(value) if value is not None else None for value in values],
                                    type=pa.string(),
                                )
                            )
                    table_backend = ArrowBackend(pa.Table.from_arrays(arrays, names=columns))
                    table = self._build_results_table(columns, initial_rows, escape=escape, backend=table_backend)
                else:
                    table = self._build_results_table(columns, initial_rows, escape=escape)
            else:
                table = self._build_results_table(columns, initial_rows, escape=escape)
        except Exception as exc:
            try:
                self.log.error(f"Results table build failed; falling back to full render: {exc}")
            except Exception:
                pass
            if render_token == getattr(self, "_results_render_token", 0):
                self._replace_results_table_with_data(columns, rows, escape=escape)
                if table_info is not None:
                    try:
                        self.results_table.result_table_info = table_info
                    except Exception:
                        pass
            return
        if render_token != getattr(self, "_results_render_token", 0):
            return
        if table_info is not None:
            table.result_table_info = table_info
        self._replace_results_table_with_table(table)
        self._schedule_results_render(
            table,
            columns,
            rows,
            escape=escape,
            coerce_to_str_columns=coerce_to_str_columns,
            start_index=initial_count,
            row_limit=row_limit,
            render_token=render_token,
        )

    async def _display_query_results(
        self: QueryMixinHost, columns: list[str], rows: list[tuple], row_count: int, truncated: bool, elapsed_ms: float
    ) -> None:
        """Display query results in the results table (called on main thread)."""
        self._last_result_columns = columns
        self._last_result_rows = rows
        self._last_result_row_count = row_count
        table_info = getattr(self, "_pending_result_table_info", None)

        # Switch to single result mode (in case we were showing stacked results)
        self._show_single_result_mode()
        self._cancel_results_render()
        render_token = getattr(self, "_results_render_token", 0)
        row_limit = min(len(rows), MAX_RENDER_ROWS)
        if row_limit > RESULTS_RENDER_CHUNK_SIZE:
            self._render_results_table_incremental(
                columns,
                rows,
                escape=True,
                row_limit=row_limit,
                render_token=render_token,
                table_info=table_info,
            )
        else:
            render_rows = rows[:row_limit] if row_limit else []
            table = self._build_results_table(columns, render_rows, escape=True)
            if render_token != getattr(self, "_results_render_token", 0):
                return
            if table_info is not None:
                table.result_table_info = table_info
            self._replace_results_table_with_table(table)

        time_str = format_duration_ms(elapsed_ms)
        if truncated:
            self.notify(
                f"Query returned {row_count}+ rows in {time_str} (truncated)",
                severity="warning",
            )
        else:
            self.notify(f"Query returned {row_count} rows in {time_str}")
        if table_info is not None:
            prime = getattr(self, "_prime_result_table_columns", None)
            if callable(prime):
                prime(table_info)
        self._pending_result_table_info = None

    def _display_non_query_result(self: QueryMixinHost, affected: int, elapsed_ms: float) -> None:
        """Display non-query result (called on main thread)."""
        self._pending_result_table_info = None
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
        self._cancel_results_render()
        self._pending_result_table_info = None
        # notify(severity="error") handles displaying the error in results via _show_error_in_results
        self.notify(f"Query error: {error_message}", severity="error")

    def _display_multi_statement_results(
        self: QueryMixinHost,
        multi_result: Any,
        elapsed_ms: float,
    ) -> None:
        """Display stacked results for multi-statement query."""
        self._cancel_results_render()
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
            table_info = self._infer_result_table_info(stmt_result.statement)
            if table_info is not None:
                prime = getattr(self, "_prime_result_table_columns", None)
                if callable(prime):
                    prime(table_info)
            container.add_result_section(
                stmt_result,
                i,
                auto_collapse=auto_collapse,
                table_info=table_info,
            )

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
        self._pending_result_table_info = None

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

    def _infer_result_table_info(self: QueryMixinHost, sql: str) -> dict[str, Any] | None:
        """Best-effort inference of a single source table for query results."""
        from sqlit.domains.query.completion import extract_table_refs

        refs = extract_table_refs(sql)
        if len(refs) != 1:
            return None
        ref = refs[0]
        schema = ref.schema
        name = ref.name
        database = None
        table_metadata = getattr(self, "_table_metadata", {}) or {}
        key_candidates = [name.lower()]
        if schema:
            key_candidates.insert(0, f"{schema}.{name}".lower())
        for key in key_candidates:
            metadata = table_metadata.get(key)
            if metadata:
                schema, name, database = metadata
                break
        return {
            "database": database,
            "schema": schema,
            "name": name,
            "columns": [],
        }
