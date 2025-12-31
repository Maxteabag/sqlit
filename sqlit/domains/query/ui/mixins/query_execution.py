"""Query execution helpers and actions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlit.shared.ui.protocols import QueryMixinHost
from sqlit.shared.ui.spinner import Spinner

from .query_constants import MAX_FETCH_ROWS

if TYPE_CHECKING:
    from textual.worker import Worker

    from sqlit.domains.query.app.cancellable import CancellableQuery
    from sqlit.domains.query.app.query_service import QueryService


class QueryExecutionMixin:
    """Mixin providing query execution actions."""

    _query_service: QueryService | None = None
    _query_service_db_type: str | None = None
    _query_worker: Worker[Any] | None = None
    _cancellable_query: CancellableQuery | None = None
    _query_spinner: Spinner | None = None
    _query_cursor_cache: dict[str, tuple[int, int]] | None = None
    _query_target_database: str | None = None
    _schema_worker: Any | None = None
    _schema_indexing: bool = False

    def action_execute_query(self: QueryMixinHost) -> None:
        """Execute the current query."""
        self._execute_query_common(keep_insert_mode=False)

    def action_execute_query_insert(self: QueryMixinHost) -> None:
        """Execute query in INSERT mode without leaving it."""
        self._execute_query_common(keep_insert_mode=True)

    def _execute_query_common(self: QueryMixinHost, keep_insert_mode: bool) -> None:
        """Common query execution logic."""
        if not self.current_connection or not self.current_provider:
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

    def _start_query_spinner(self: QueryMixinHost) -> None:
        """Start the query execution spinner animation."""
        import time

        self._query_executing = True
        self._query_start_time = time.perf_counter()
        if self._query_spinner is not None:
            self._query_spinner.stop()
        self._query_spinner = Spinner(self, on_tick=lambda _: self._update_status_bar(), fps=30)
        self._query_spinner.start()

    def _stop_query_spinner(self: QueryMixinHost) -> None:
        """Stop the query execution spinner animation."""
        self._query_executing = False
        if self._query_spinner is not None:
            self._query_spinner.stop()
            self._query_spinner = None
        self._update_status_bar()

    def _get_history_store(self: QueryMixinHost) -> Any:
        store = getattr(self, "_history_store", None)
        if store is not None:
            return store
        return self.services.history_store

    def _get_query_service(self: QueryMixinHost, provider: Any) -> QueryService:
        if self._query_service is None or (
            self._query_service_db_type is not None
            and self._query_service_db_type != provider.metadata.db_type
        ):
            from sqlit.domains.query.app.query_service import DialectQueryAnalyzer, QueryService

            self._query_service = QueryService(
                self._get_history_store(),
                analyzer=DialectQueryAnalyzer(provider.dialect),
            )
            self._query_service_db_type = provider.metadata.db_type
        return self._query_service

    async def _run_query_async(self: QueryMixinHost, query: str, keep_insert_mode: bool) -> None:
        """Run query asynchronously using a cancellable dedicated connection."""
        import asyncio
        import time

        from sqlit.domains.query.app.cancellable import CancellableQuery
        from sqlit.domains.query.app.query_service import QueryResult, parse_use_statement

        provider = self.current_provider
        config = self.current_config

        if not provider or not config:
            self._display_query_error("Not connected")
            self._stop_query_spinner()
            return

        # If we have a target database from clicking a table in the tree,
        # use that database for the query execution (needed for Azure SQL)
        target_db = getattr(self, "_query_target_database", None)
        endpoint = config.tcp_endpoint
        current_db = endpoint.database if endpoint else ""
        if target_db and target_db != current_db:
            config = provider.apply_database_override(config, target_db)
        # Clear target database after use - it's only for the auto-generated query
        self._query_target_database = None

        # Apply active database to query execution (from USE statement or 'u' key)
        active_db = None
        if hasattr(self, "_get_effective_database"):
            active_db = self._get_effective_database()
        endpoint = config.tcp_endpoint
        current_db = endpoint.database if endpoint else ""
        if active_db and active_db != current_db and not target_db:
            config = provider.apply_database_override(config, active_db)

        # Handle USE database statements
        db_name = parse_use_statement(query)
        if db_name is not None:
            self._stop_query_spinner()
            self._display_non_query_result(0, 0)
            self.set_default_database(db_name)
            if keep_insert_mode:
                self._restore_insert_mode()
            return

        # Dedicated connection enables cancellation by closing it.
        cancellable = CancellableQuery(
            sql=query,
            config=config,
            provider=provider,
            tunnel=self.current_ssh_tunnel,
        )
        self._cancellable_query = cancellable

        service = self._get_query_service(provider)

        try:
            start_time = time.perf_counter()
            max_rows = self.services.runtime.max_rows or MAX_FETCH_ROWS
            result = await asyncio.to_thread(
                cancellable.execute,
                max_rows,
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

    def _restore_insert_mode(self: QueryMixinHost) -> None:
        """Restore INSERT mode after query execution (called on main thread)."""
        from sqlit.core.vim import VimMode

        self.vim_mode = VimMode.INSERT
        self.query_input.read_only = False
        self.query_input.focus()
        self._update_footer_bindings()
        self._update_status_bar()

    def action_cancel_query(self: QueryMixinHost) -> None:
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

        self._replace_results_table(["Status"], [("Query cancelled",)])

        self.notify("Query cancelled", severity="warning")

    def action_cancel_operation(self: QueryMixinHost) -> None:
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
            self._replace_results_table(["Status"], [("Query cancelled",)])
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

    def action_clear_query(self: QueryMixinHost) -> None:
        """Clear the query input."""
        self.query_input.text = ""

    def action_new_query(self: QueryMixinHost) -> None:
        """Start a new query (clear input and results)."""
        self.query_input.text = ""
        self._replace_results_table([], [])

    def action_show_history(self: QueryMixinHost) -> None:
        """Show query history for the current connection."""
        if not self.current_config:
            self.notify("Not connected", severity="warning")
            return

        from ..screens import QueryHistoryScreen

        history_store = self._get_history_store()
        starred_store = self.services.starred_store
        history = history_store.load_for_connection(self.current_config.name)
        starred = starred_store.load_for_connection(self.current_config.name)
        self.push_screen(
            QueryHistoryScreen(history, self.current_config.name, starred),
            self._handle_history_result,
        )

    def _handle_history_result(self: QueryMixinHost, result: Any) -> None:
        """Handle the result from the history screen."""
        if result is None:
            return

        action, data = result
        if action == "select":
            # Initialize cursor cache if needed
            if self._query_cursor_cache is None:
                self._query_cursor_cache = {}
            cursor_cache = self._query_cursor_cache

            # Save current query's cursor position before switching
            current_query = self.query_input.text
            if current_query:
                cursor_cache[current_query] = self.query_input.cursor_location

            # Set new query text
            self.query_input.text = data

            # Restore cursor position if we have it cached, otherwise go to end
            if data in cursor_cache:
                self.query_input.cursor_location = cursor_cache[data]
            else:
                # Move cursor to end of query
                lines = data.split("\n")
                last_line = len(lines) - 1
                last_col = len(lines[-1]) if lines else 0
                self.query_input.cursor_location = (last_line, last_col)
        elif action == "delete":
            self._delete_history_entry(data)
            self.action_show_history()
        elif action == "toggle_star":
            self._toggle_star(data)
            self.action_show_history()

    def _delete_history_entry(self: QueryMixinHost, timestamp: str) -> None:
        """Delete a specific history entry by timestamp."""
        if not self.current_config:
            return
        self._get_history_store().delete_entry(self.current_config.name, timestamp)

    def _toggle_star(self: QueryMixinHost, query: str) -> None:
        """Toggle star status for a query."""
        if not self.current_config:
            return

        is_now_starred = self.services.starred_store.toggle_star(self.current_config.name, query)
        if is_now_starred:
            self.notify("Query starred")
        else:
            self.notify("Query unstarred")
