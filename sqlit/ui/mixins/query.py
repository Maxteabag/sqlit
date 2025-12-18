"""Query execution mixin for SSMSTUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich.markup import escape as escape_markup
from textual.timer import Timer
from textual.worker import Worker

from ..protocols import AppProtocol
from ...utils import format_duration_ms

if TYPE_CHECKING:
    from ...services import QueryService

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class QueryMixin:
    """Mixin providing query execution functionality.

    Attributes:
        _query_service: Optional QueryService instance.
            Set this in tests to inject a mock query service.
            Defaults to a new QueryService() when None.
    """

    _query_service: QueryService | None = None

    _query_worker: Worker[Any] | None = None
    _schema_worker: Worker[Any] | None = None
    _cancellable_query: Any | None = None
    _spinner_timer: Timer | None = None
    _query_cursor_cache: dict[str, tuple[int, int]] | None = None  # query text -> cursor (row, col)

    def action_execute_query(self: AppProtocol) -> None:
        """Execute the current query."""
        self._execute_query_common(keep_insert_mode=False)

    def action_execute_query_insert(self: AppProtocol) -> None:
        """Execute query in INSERT mode without leaving it."""
        self._execute_query_common(keep_insert_mode=True)

    def action_copy_query(self: AppProtocol) -> None:
        """Copy the current query to clipboard."""
        from ...widgets import flash_widget

        query = self.query_input.text.strip()
        if not query:
            self.notify("Query is empty", severity="warning")
            return
        self._copy_text(query)
        flash_widget(self.query_input)

    def action_copy_context(self: AppProtocol) -> None:
        """Copy based on current focus (query or results)."""
        if self.query_input.has_focus:
            self.action_copy_query()
            return
        if self.results_table.has_focus:
            self.action_copy_cell()
            return
        self.notify("Nothing to copy", severity="warning")

    def _execute_query_common(self: AppProtocol, keep_insert_mode: bool) -> None:
        """Common query execution logic."""
        if not self.current_connection or not self.current_adapter:
            self.notify("Connect to a server to execute queries", severity="warning")
            return

        query = self.query_input.text.strip()

        if not query:
            self.notify("No query to execute", severity="warning")
            return

        if hasattr(self, "_query_worker") and self._query_worker is not None:
            self._query_worker.cancel()

        self._start_query_spinner()

        self._query_worker = self.run_worker(
            self._run_query_async(query, keep_insert_mode),
            name="query_execution",
            exclusive=True,
        )

    def _start_query_spinner(self: AppProtocol) -> None:
        """Start the query execution spinner animation."""
        import time

        self._query_executing = True
        self._query_start_time = time.perf_counter()
        self._spinner_index = 0
        self._update_status_bar()
        if hasattr(self, "_spinner_timer") and self._spinner_timer is not None:
            self._spinner_timer.stop()
        self._spinner_timer = self.set_interval(1 / 30, self._animate_spinner)  # 30fps

    def _stop_query_spinner(self: AppProtocol) -> None:
        """Stop the query execution spinner animation."""
        self._query_executing = False
        if hasattr(self, "_spinner_timer") and self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None
        self._update_status_bar()

    def _animate_spinner(self: AppProtocol) -> None:
        """Update spinner animation frame."""
        if not self._query_executing:
            return
        self._spinner_index = (self._spinner_index + 1) % len(SPINNER_FRAMES)
        self._update_status_bar()

    async def _run_query_async(self: AppProtocol, query: str, keep_insert_mode: bool) -> None:
        """Run query asynchronously using a cancellable dedicated connection."""
        import asyncio
        import time

        from ...services import CancellableQuery, QueryResult, QueryService

        adapter = self.current_adapter
        config = self.current_config

        if not adapter or not config:
            self._display_query_error("Not connected")
            self._stop_query_spinner()
            return

        # Dedicated connection enables cancellation by closing it.
        cancellable = CancellableQuery(
            sql=query,
            config=config,
            adapter=adapter,
        )
        self._cancellable_query = cancellable

        service = self._query_service or QueryService()

        try:
            max_fetch_rows = 10000

            start_time = time.perf_counter()
            result = await asyncio.to_thread(
                cancellable.execute,
                max_fetch_rows,
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            service._save_to_history(config.name, query)

            if isinstance(result, QueryResult):
                self._display_query_results(result.columns, result.rows, result.row_count, result.truncated, elapsed_ms)
            else:
                self._display_non_query_result(result.rows_affected, elapsed_ms)

            if keep_insert_mode:
                self._restore_insert_mode()

        except RuntimeError as e:
            if "cancelled" in str(e).lower():
                pass  # Already handled by action_cancel_query
            else:
                self._display_query_error(str(e))
        except Exception as e:
            if not cancellable.is_cancelled:
                self._display_query_error(str(e))
        finally:
            self._cancellable_query = None
            self._stop_query_spinner()

    def _display_query_results(
        self: AppProtocol, columns: list[str], rows: list[tuple], row_count: int, truncated: bool, elapsed_ms: float
    ) -> None:
        """Display query results in the results table (called on main thread)."""
        self._last_result_columns = columns
        self._last_result_rows = rows
        self._last_result_row_count = row_count

        self.results_table.clear(columns=True)
        self.results_table.show_header = True
        self.results_table.add_columns(*columns)

        for row in rows[:1000]:
            str_row = tuple(escape_markup(str(v)) if v is not None else "NULL" for v in row)
            self.results_table.add_row(*str_row)

        time_str = format_duration_ms(elapsed_ms)
        if truncated:
            self.notify(f"Query returned {row_count}+ rows in {time_str} (truncated)", severity="warning")
        else:
            self.notify(f"Query returned {row_count} rows in {time_str}")

    def _display_non_query_result(self: AppProtocol, affected: int, elapsed_ms: float) -> None:
        """Display non-query result (called on main thread)."""
        self._last_result_columns = ["Result"]
        self._last_result_rows = [(f"{affected} row(s) affected",)]
        self._last_result_row_count = 1

        self.results_table.clear(columns=True)
        self.results_table.show_header = True
        self.results_table.add_column("Result")
        self.results_table.add_row(f"{affected} row(s) affected")
        time_str = format_duration_ms(elapsed_ms)
        self.notify(f"Query executed: {affected} row(s) affected in {time_str}")

    def _display_query_error(self: AppProtocol, error_message: str) -> None:
        """Display query error (called on main thread)."""
        self._last_result_columns = ["Error"]
        self._last_result_rows = [(error_message,)]
        self._last_result_row_count = 1

        self.results_table.clear(columns=True)
        self.results_table.show_header = True
        self.results_table.add_column("Error")
        self.results_table.add_row(escape_markup(error_message))
        self.notify(f"Query error: {error_message}", severity="error")

    def _restore_insert_mode(self: AppProtocol) -> None:
        """Restore INSERT mode after query execution (called on main thread)."""
        from ...widgets import VimMode

        self.vim_mode = VimMode.INSERT
        self.query_input.read_only = False
        self.query_input.focus()
        self._update_footer_bindings()
        self._update_status_bar()

    def action_cancel_query(self: AppProtocol) -> None:
        """Cancel the currently running query."""
        if not getattr(self, "_query_executing", False):
            self.notify("No query running")
            return

        if hasattr(self, "_cancellable_query") and self._cancellable_query is not None:
            self._cancellable_query.cancel()

        if hasattr(self, "_query_worker") and self._query_worker is not None:
            self._query_worker.cancel()
            self._query_worker = None

        self._stop_query_spinner()

        self.results_table.clear(columns=True)
        self.results_table.show_header = True
        self.results_table.add_column("Status")
        self.results_table.add_row("Query cancelled")

        self.notify("Query cancelled", severity="warning")

    def action_cancel_operation(self: AppProtocol) -> None:
        """Cancel any running operation (query or schema indexing)."""
        cancelled = False

        # Cancel query if running
        if getattr(self, "_query_executing", False):
            # Cancel the cancellable query (closes dedicated connection)
            if hasattr(self, "_cancellable_query") and self._cancellable_query is not None:
                self._cancellable_query.cancel()

            if hasattr(self, "_query_worker") and self._query_worker is not None:
                self._query_worker.cancel()
                self._query_worker = None
            self._stop_query_spinner()

            # Update results table to show cancelled state
            self.results_table.clear(columns=True)
            self.results_table.show_header = True
            self.results_table.add_column("Status")
            self.results_table.add_row("Query cancelled")
            cancelled = True

        # Cancel schema indexing if running
        if getattr(self, "_schema_indexing", False):
            if hasattr(self, "_schema_worker") and self._schema_worker is not None:
                self._schema_worker.cancel()
                self._schema_worker = None
            self._stop_schema_spinner()
            cancelled = True

        if cancelled:
            self.notify("Operation cancelled", severity="warning")
        else:
            self.notify("No operation running")

    def action_clear_query(self: AppProtocol) -> None:
        """Clear the query input."""
        self.query_input.text = ""

    def action_new_query(self: AppProtocol) -> None:
        """Start a new query (clear input and results)."""
        self.query_input.text = ""
        self.results_table.clear(columns=True)
        self.results_table.show_header = False

    def action_show_history(self: AppProtocol) -> None:
        """Show query history for the current connection."""
        if not self.current_config:
            self.notify("Not connected to a database", severity="warning")
            return

        from ...config import load_query_history
        from ..screens import QueryHistoryScreen

        history = load_query_history(self.current_config.name)
        self.push_screen(
            QueryHistoryScreen(history, self.current_config.name),
            self._handle_history_result,
        )

    def _handle_history_result(self: AppProtocol, result: Any) -> None:
        """Handle the result from the history screen."""
        if result is None:
            return

        action, data = result
        if action == "select":
            # Initialize cursor cache if needed
            if self._query_cursor_cache is None:
                self._query_cursor_cache = {}

            # Save current query's cursor position before switching
            current_query = self.query_input.text
            if current_query:
                self._query_cursor_cache[current_query] = self.query_input.cursor_location

            # Set new query text
            self.query_input.text = data

            # Restore cursor position if we have it cached, otherwise go to end
            if data in self._query_cursor_cache:
                self.query_input.cursor_location = self._query_cursor_cache[data]
            else:
                # Move cursor to end of query
                lines = data.split("\n")
                last_line = len(lines) - 1
                last_col = len(lines[-1]) if lines else 0
                self.query_input.cursor_location = (last_line, last_col)
        elif action == "delete":
            self._delete_history_entry(data)
            self.action_show_history()

    def _delete_history_entry(self: AppProtocol, timestamp: str) -> None:
        """Delete a specific history entry by timestamp."""
        from ...config import delete_query_from_history

        if not self.current_config:
            return
        delete_query_from_history(self.current_config.name, timestamp)
