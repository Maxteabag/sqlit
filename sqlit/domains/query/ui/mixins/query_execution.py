"""Query execution helpers and actions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from sqlit.domains.explorer.ui.tree import db_switching as tree_db_switching
from sqlit.domains.process_worker.ui.mixins.process_worker_lifecycle import (
    ProcessWorkerLifecycleMixin,
)
from sqlit.shared.ui.protocols import QueryMixinHost
from sqlit.shared.ui.spinner import Spinner

from .query_constants import MAX_FETCH_ROWS

if TYPE_CHECKING:
    from textual.worker import Worker

    from sqlit.domains.query.app.cancellable import CancellableQuery
    from sqlit.domains.query.app.query_service import QueryService
    from sqlit.domains.query.app.transaction import TransactionExecutor


class QueryExecutionMixin(ProcessWorkerLifecycleMixin):
    """Mixin providing query execution actions."""

    _query_service: QueryService | None = None
    _query_service_db_type: str | None = None
    _query_worker: Worker[Any] | None = None
    _cancellable_query: CancellableQuery | None = None
    _transaction_executor: TransactionExecutor | None = None
    _transaction_executor_config: Any | None = None
    _query_spinner: Spinner | None = None
    _query_cursor_cache: dict[str, tuple[int, int]] | None = None
    _query_target_database: str | None = None
    _schema_worker: Any | None = None
    _schema_indexing: bool = False
    _pending_telescope_query: tuple[str, str] | None = None
    _telescope_auto_filter: bool = False

    def action_execute_query(self: QueryMixinHost) -> None:
        """Execute the current query."""
        self._execute_query_common(keep_insert_mode=False)

    def action_execute_query_insert(self: QueryMixinHost) -> None:
        """Execute query in INSERT mode without leaving it."""
        self._execute_query_common(keep_insert_mode=True)

    def action_execute_query_atomic(self: QueryMixinHost) -> None:
        """Execute query atomically (wrapped in BEGIN/COMMIT with rollback on error)."""
        if self.current_connection is None or self.current_provider is None:
            self.notify("Connect to a server to execute queries", severity="warning")
            return

        query = self._get_query_to_execute()

        if not query:
            self.notify("No query to execute", severity="warning")
            return

        def _proceed() -> None:
            if hasattr(self, "_query_worker") and self._query_worker is not None:
                self._query_worker.cancel()

            self._start_query_spinner()

            self._query_worker = self.run_worker(
                self._run_query_atomic_async(query),
                name="query_execution_atomic",
                exclusive=True,
            )

        self._maybe_confirm_query(query, _proceed)

    def action_execute_single_statement(self: QueryMixinHost) -> None:
        """Execute only the SQL statement at the current cursor position."""
        from sqlit.domains.query.app.multi_statement import find_statement_at_cursor

        if self.current_connection is None or self.current_provider is None:
            self.notify("Connect to a server to execute queries", severity="warning")
            return

        full_query = self.query_input.text
        if not full_query or not full_query.strip():
            self.notify("No query to execute", severity="warning")
            return

        # Get cursor position and find statement
        row, col = self.query_input.cursor_location
        result = find_statement_at_cursor(full_query, row, col)

        if result is None:
            self.notify("No statement found at cursor", severity="warning")
            return

        statement, _, _ = result

        if not statement.strip():
            self.notify("No statement found at cursor", severity="warning")
            return

        def _proceed() -> None:
            if hasattr(self, "_query_worker") and self._query_worker is not None:
                self._query_worker.cancel()

            self._start_query_spinner()

            self._query_worker = self.run_worker(
                self._run_query_async(statement, keep_insert_mode=False),
                name="query_execution_single",
                exclusive=True,
            )

        self._maybe_confirm_query(statement, _proceed)

    def _get_query_to_execute(self: QueryMixinHost) -> str:
        """Return selected text if present, otherwise the full query."""
        selection = self.query_input.selection
        if selection.start != selection.end:
            from sqlit.domains.query.editing import get_selection_text

            start = selection.start
            end = selection.end
            if start > end:
                start, end = end, start

            selected_sql = get_selection_text(
                self.query_input.text,
                start[0],
                start[1],
                end[0],
                end[1],
            )
            if selected_sql and selected_sql.strip():
                return selected_sql.strip()

        return self.query_input.text.strip()

    def _execute_query_common(self: QueryMixinHost, keep_insert_mode: bool) -> None:
        """Common query execution logic."""
        if self.current_connection is None or self.current_provider is None:
            self.notify("Connect to a server to execute queries", severity="warning")
            return

        query = self._get_query_to_execute()

        if not query:
            self.notify("No query to execute", severity="warning")
            return

        def _proceed() -> None:
            if hasattr(self, "_query_worker") and self._query_worker is not None:
                self._query_worker.cancel()

            self._start_query_spinner()

            self._query_worker = self.run_worker(
                self._run_query_async(query, keep_insert_mode),
                name="query_execution",
                exclusive=True,
            )

        self._maybe_confirm_query(query, _proceed)

    def _maybe_confirm_query(self: QueryMixinHost, query: str, proceed: Callable[[], None]) -> None:
        """Confirm query execution based on alert mode, then call proceed."""
        from sqlit.domains.query.app.alerts import (
            AlertMode,
            AlertSeverity,
            classify_query_alert,
            format_alert_mode,
            should_confirm,
        )
        from sqlit.domains.query.app.multi_statement import get_executable_sql
        from sqlit.shared.ui.screens.confirm import ConfirmScreen

        raw_mode = getattr(self.services.runtime, "query_alert_mode", 0) or 0
        try:
            mode = AlertMode(int(raw_mode))
        except ValueError:
            mode = AlertMode.OFF

        if mode == AlertMode.OFF:
            proceed()
            return

        # Get the SQL that will actually execute (without comment-only statements)
        executable_sql = get_executable_sql(query)
        if not executable_sql:
            # Nothing to execute after filtering comments
            proceed()
            return

        severity = classify_query_alert(executable_sql)
        if severity == AlertSeverity.NONE or not should_confirm(mode, severity):
            proceed()
            return

        title = "Confirm query"
        if severity == AlertSeverity.DELETE:
            title = "Confirm DELETE query"
        elif severity == AlertSeverity.WRITE:
            title = "Confirm write query"

        def _on_result(confirmed: bool | None) -> None:
            if confirmed:
                proceed()
                return
            self.notify(
                f"Query cancelled (alert mode: {format_alert_mode(mode)})",
                severity="warning",
            )

        self.push_screen(
            ConfirmScreen(title, executable_sql, yes_label="Yes", no_label="No"),
            _on_result,
        )

    def _start_query_spinner(self: QueryMixinHost) -> None:
        """Start the query execution spinner animation."""
        import time

        self.query_executing = True
        self._query_start_time = time.perf_counter()
        if self._query_spinner is not None:
            self._query_spinner.stop()
        self._query_spinner = Spinner(self, on_tick=lambda _: self._update_status_bar(), fps=30)
        self._query_spinner.start()
        self._update_footer_bindings()

    def _stop_query_spinner(self: QueryMixinHost) -> None:
        """Stop the query execution spinner animation."""
        self.query_executing = False
        if self._query_spinner is not None:
            self._query_spinner.stop()
            self._query_spinner = None
        if getattr(self, "_defer_schema_load", False):
            setattr(self, "_defer_schema_load", False)
            loader = getattr(self, "_load_schema_cache", None)
            if callable(loader):
                try:
                    loader()
                except Exception:
                    pass

    def _get_history_store(self: QueryMixinHost) -> Any:
        store = getattr(self, "_history_store", None)
        if store is not None:
            return store
        return self.services.history_store

    def _get_unsaved_history_store(self: QueryMixinHost) -> Any:
        store = getattr(self, "_unsaved_history_store", None)
        if store is None:
            from sqlit.domains.query.store.memory import InMemoryHistoryStore

            store = InMemoryHistoryStore()
            self._unsaved_history_store = store
        return store

    def _should_save_query_history(self: QueryMixinHost, config: Any) -> bool:
        """Return True if the connection is saved and history should be persisted."""
        name = getattr(config, "name", "")
        if not name:
            return False
        connections = getattr(self, "connections", None) or []
        return any(getattr(conn, "name", None) == name for conn in connections)

    def _save_query_history(self: QueryMixinHost, config: Any, query: str) -> None:
        """Save query history only for saved connections."""
        if self._should_save_query_history(config):
            self._get_history_store().save_query(config.name, query)
            return
        self._get_unsaved_history_store().save_query(config.name, query)

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

    def _get_transaction_executor(self: QueryMixinHost, config: Any, provider: Any) -> Any:
        """Get or create a TransactionExecutor for the current connection."""
        from sqlit.domains.query.app.transaction import TransactionExecutor

        # Create new executor if none exists or if config changed
        if self._transaction_executor is None or self._transaction_executor_config != config:
            if self._transaction_executor is not None:
                self._transaction_executor.close()
            self._transaction_executor = TransactionExecutor(config=config, provider=provider)
            self._transaction_executor_config = config
        return self._transaction_executor

    def _reset_transaction_executor(self: QueryMixinHost) -> None:
        """Reset the transaction executor (e.g., on disconnect)."""
        if self._transaction_executor is not None:
            self._transaction_executor.close()
            self._transaction_executor = None
        self._transaction_executor_config = None

    def _on_disconnect(self: QueryMixinHost) -> None:
        """Handle disconnect lifecycle event."""
        parent_disconnect = getattr(super(), "_on_disconnect", None)
        if callable(parent_disconnect):
            parent_disconnect()
        self._reset_transaction_executor()

    def _on_connect(self: QueryMixinHost) -> None:
        """Handle connect lifecycle event."""
        parent_connect = getattr(super(), "_on_connect", None)
        if callable(parent_connect):
            parent_connect()

        self._maybe_run_pending_telescope_query()

    def watch_current_connection(self: QueryMixinHost, old_value: Any, new_value: Any) -> None:
        self._maybe_run_pending_telescope_query()

    def watch_current_provider(self: QueryMixinHost, old_value: Any, new_value: Any) -> None:
        self._maybe_run_pending_telescope_query()

    def _on_connect_failed(self: QueryMixinHost, config: Any) -> None:
        pending = getattr(self, "_pending_telescope_query", None)
        if not pending:
            return
        if getattr(config, "name", None) == pending[0]:
            self._pending_telescope_query = None

    def _maybe_run_pending_telescope_query(self: QueryMixinHost) -> None:
        if not getattr(self, "_screen_stack", None):
            return
        pending = getattr(self, "_pending_telescope_query", None)
        if not pending:
            return
        if (
            self.current_connection is None
            or self.current_provider is None
            or self.current_config is None
        ):
            return
        connection_name, query = pending
        if self.current_config.name != connection_name:
            return
        self._pending_telescope_query = None
        self._apply_history_query(query)

    @property
    def in_transaction(self: QueryMixinHost) -> bool:
        """Whether we're currently in a transaction."""
        if self._transaction_executor is not None:
            return bool(self._transaction_executor.in_transaction)
        return False

    async def _run_query_async(self: QueryMixinHost, query: str, keep_insert_mode: bool) -> None:
        """Run query asynchronously using TransactionExecutor for transaction support."""
        import asyncio
        import time

        from sqlit.domains.query.app.multi_statement import (
            MultiStatementExecutor,
            split_statements,
        )
        from sqlit.domains.query.app.query_service import QueryResult, parse_use_statement
        from sqlit.domains.query.app.transaction import is_transaction_end, is_transaction_start

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
            tree_db_switching.set_default_database(self, db_name)
            if keep_insert_mode:
                self._restore_insert_mode()
            return

        # Use TransactionExecutor for transaction-aware query execution
        executor = self._get_transaction_executor(config, provider)
        # Check if this is a multi-statement query (after filtering comment-only statements)
        from sqlit.domains.query.editing.comments import is_comment_only_statement

        statements = split_statements(query)
        executable_statements = [s for s in statements if not is_comment_only_statement(s)]
        is_multi_statement = len(executable_statements) > 1

        if is_multi_statement:
            self._pending_result_table_info = None
        elif executable_statements:
            if getattr(self, "_pending_result_table_info", None) is None:
                table_info = self._infer_result_table_info(executable_statements[0])
                if table_info is not None:
                    self._pending_result_table_info = table_info
                    prime = getattr(self, "_prime_result_table_columns", None)
                    if callable(prime):
                        prime(table_info)

        try:
            start_time = time.perf_counter()
            max_rows = self.services.runtime.max_rows or MAX_FETCH_ROWS

            use_process_worker = self._use_process_worker(provider)
            if use_process_worker and executable_statements:
                statement = executable_statements[0].strip()
                if self.in_transaction or is_transaction_start(statement) or is_transaction_end(statement):
                    use_process_worker = False

            if use_process_worker and not is_multi_statement:
                client = await self._get_process_worker_client_async()
                if client is None:
                    error = getattr(self, "_process_worker_client_error", None)
                    if error:
                        self.notify(
                            f"Process worker unavailable; falling back. ({error})",
                            severity="error",
                            title="Process Worker",
                        )
                    else:
                        self.notify(
                            "Process worker unavailable; falling back.",
                            severity="error",
                            title="Process Worker",
                        )
                    use_process_worker = False

                if use_process_worker:
                    outcome = await asyncio.to_thread(client.execute, query, config, max_rows)
                    if outcome.cancelled:
                        return
                    if outcome.error:
                        self._display_query_error(outcome.error)
                        return

                    try:
                        await asyncio.to_thread(self._save_query_history, config, query)
                    except Exception:
                        pass
                    result = outcome.result
                    elapsed_ms = outcome.elapsed_ms

                    if isinstance(result, QueryResult):
                        await self._display_query_results(
                            result.columns,
                            result.rows,
                            result.row_count,
                            result.truncated,
                            elapsed_ms,
                        )
                    else:
                        self._display_non_query_result(result.rows_affected, elapsed_ms)
                    if keep_insert_mode:
                        self._restore_insert_mode()
                    return

            if is_multi_statement:
                # Multi-statement execution with stacked results
                multi_executor = MultiStatementExecutor(executor)
                multi_result = await asyncio.to_thread(
                    multi_executor.execute,
                    query,
                    max_rows,
                )
                elapsed_ms = (time.perf_counter() - start_time) * 1000

                try:
                    await asyncio.to_thread(self._save_query_history, config, query)
                except Exception:
                    pass
                self._display_multi_statement_results(multi_result, elapsed_ms)
            else:
                # Single statement - existing behavior
                result = await asyncio.to_thread(
                    executor.execute,
                    query,
                    max_rows,
                )
                elapsed_ms = (time.perf_counter() - start_time) * 1000

                try:
                    await asyncio.to_thread(self._save_query_history, config, query)
                except Exception:
                    pass

                if isinstance(result, QueryResult):
                    await self._display_query_results(
                        result.columns, result.rows, result.row_count, result.truncated, elapsed_ms
                    )
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
            self._display_query_error(str(e))
        finally:
            self._stop_query_spinner()

    async def _run_query_atomic_async(self: QueryMixinHost, query: str) -> None:
        """Run query atomically (BEGIN/COMMIT with rollback on error)."""
        import asyncio
        import time

        from sqlit.domains.query.app.multi_statement import MultiStatementResult
        from sqlit.domains.query.app.query_service import QueryResult
        from sqlit.domains.query.app.transaction import TransactionExecutor

        provider = self.current_provider
        config = self.current_config

        if not provider or not config:
            self._display_query_error("Not connected")
            self._stop_query_spinner()
            return

        # Apply active database if set
        active_db = None
        if hasattr(self, "_get_effective_database"):
            active_db = self._get_effective_database()
        endpoint = config.tcp_endpoint
        current_db = endpoint.database if endpoint else ""
        if active_db and active_db != current_db:
            config = provider.apply_database_override(config, active_db)

        # Create a dedicated executor for atomic execution
        executor = TransactionExecutor(config=config, provider=provider)
        try:
            start_time = time.perf_counter()
            max_rows = self.services.runtime.max_rows or MAX_FETCH_ROWS
            result = await asyncio.to_thread(
                executor.atomic_execute,
                query,
                max_rows,
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            try:
                await asyncio.to_thread(self._save_query_history, config, query)
            except Exception:
                pass

            if isinstance(result, MultiStatementResult):
                # Multi-statement atomic execution
                self._display_multi_statement_results(result, elapsed_ms)
                if result.has_error:
                    self.notify("Transaction rolled back (error in statement)", severity="error")
                else:
                    self.notify("Query executed atomically (committed)", severity="information")
            elif isinstance(result, QueryResult):
                await self._display_query_results(
                    result.columns, result.rows, result.row_count, result.truncated, elapsed_ms
                )
                self.notify("Query executed atomically (committed)", severity="information")
            else:
                self._display_non_query_result(result.rows_affected, elapsed_ms)
                self.notify("Query executed atomically (committed)", severity="information")

        except Exception as e:
            self._display_query_error(f"Transaction rolled back: {e}")
        finally:
            executor.close()
            self._stop_query_spinner()

    def _restore_insert_mode(self: QueryMixinHost) -> None:
        """Restore INSERT mode after query execution (called on main thread)."""
        from sqlit.core.vim import VimMode

        self.vim_mode = VimMode.INSERT
        self.query_input.read_only = False
        self.query_input.focus()
        self._update_footer_bindings()
        self._update_vim_mode_visuals()

    def action_cancel_query(self: QueryMixinHost) -> None:
        """Cancel the currently running query."""
        if not getattr(self, "query_executing", False):
            self.notify("No query running")
            return

        client = getattr(self, "_process_worker_client", None)
        if client is not None:
            try:
                client.cancel_current()
            except Exception:
                pass

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
        if getattr(self, "query_executing", False):
            # Cancel the cancellable query (closes dedicated connection)
            client = getattr(self, "_process_worker_client", None)
            if client is not None:
                try:
                    client.cancel_current()
                except Exception:
                    pass
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

    def _apply_history_query(self: QueryMixinHost, query: str) -> None:
        """Load a query into the editor and restore cursor position if possible."""
        # Initialize cursor cache if needed
        if self._query_cursor_cache is None:
            self._query_cursor_cache = {}
        cursor_cache = self._query_cursor_cache

        # Save current query's cursor position before switching
        current_query = self.query_input.text
        if current_query:
            cursor_cache[current_query] = self.query_input.cursor_location

        # Set new query text
        self.query_input.text = query

        # Restore cursor position if we have it cached, otherwise go to end
        if query in cursor_cache:
            self.query_input.cursor_location = cursor_cache[query]
        else:
            lines = query.split("\n")
            last_line = len(lines) - 1
            last_col = len(lines[-1]) if lines else 0
            self.query_input.cursor_location = (last_line, last_col)

        # Focus query input - this triggers on_descendant_focus which updates footer bindings
        self.query_input.focus()

    def action_show_history(self: QueryMixinHost) -> None:
        """Show query history for the current connection."""
        if not self.current_config:
            self.notify("Not connected", severity="warning")
            return

        from ..screens import QueryHistoryScreen

        starred_store = self.services.starred_store
        if self._should_save_query_history(self.current_config):
            history = self._get_history_store().load_for_connection(self.current_config.name)
        else:
            history = self._get_unsaved_history_store().load_for_connection(self.current_config.name)
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
            self._apply_history_query(data)
        elif action == "delete":
            self._delete_history_entry(data)
            self.action_show_history()
        elif action == "toggle_star":
            self._toggle_star(data)
            self.action_show_history()

    def action_telescope(self: QueryMixinHost) -> None:
        """Show query history across all connections."""
        self._show_telescope(auto_open_filter=False)

    def action_telescope_filter(self: QueryMixinHost) -> None:
        """Show query history across all connections with filter active."""
        self._show_telescope(auto_open_filter=True)

    def _show_telescope(self: QueryMixinHost, *, auto_open_filter: bool) -> None:
        """Open telescope with optional filter preset."""
        from ..screens import QueryHistoryScreen

        connection_map = self._get_telescope_connection_map()
        available_connections = set(connection_map.keys())

        history_store = self._get_history_store()
        if hasattr(history_store, "load_all"):
            history = history_store.load_all()
        else:
            history = []
            for config in connection_map.values():
                history.extend(history_store.load_for_connection(config.name))
            history.sort(key=lambda entry: entry.timestamp, reverse=True)

        unsaved_store = getattr(self, "_unsaved_history_store", None)
        if unsaved_store is not None and hasattr(unsaved_store, "load_all"):
            history.extend(unsaved_store.load_all())

        if available_connections:
            history = [
                entry for entry in history
                if getattr(entry, "connection_name", None) in available_connections
            ]
        history.sort(key=lambda entry: entry.timestamp, reverse=True)
        connection_labels = {
            name: self._format_telescope_connection_label(config)
            for name, config in connection_map.items()
        }
        starred_by_connection = self._load_starred_by_connection(connection_map)
        self._telescope_auto_filter = auto_open_filter

        self.push_screen(
            QueryHistoryScreen(
                history,
                "All Servers",
                None,
                multi_connection=True,
                connection_labels=connection_labels,
                starred_by_connection=starred_by_connection,
                auto_open_filter=auto_open_filter,
            ),
            self._handle_telescope_result,
        )

    def _handle_telescope_result(self: QueryMixinHost, result: Any) -> None:
        """Handle the result from the telescope screen."""
        if result is None:
            return

        action, data = result
        if action == "select":
            query = data.get("query", "")
            connection_name = data.get("connection_name", "")
            self._run_telescope_query(connection_name, query)
        elif action == "delete":
            timestamp = data.get("timestamp", "")
            connection_name = data.get("connection_name", "")
            if timestamp and connection_name:
                self._get_history_store().delete_entry(connection_name, timestamp)
            if self._telescope_auto_filter:
                self.action_telescope_filter()
            else:
                self.action_telescope()
        elif action == "toggle_star":
            query = data.get("query", "")
            connection_name = data.get("connection_name", "")
            if query and connection_name:
                is_now_starred = self.services.starred_store.toggle_star(connection_name, query)
                if is_now_starred:
                    self.notify("Query starred")
                else:
                    self.notify("Query unstarred")
            if self._telescope_auto_filter:
                self.action_telescope_filter()
            else:
                self.action_telescope()

    def _run_telescope_query(self: QueryMixinHost, connection_name: str, query: str) -> None:
        if not query or not connection_name:
            return

        config = self._get_telescope_connection_map().get(connection_name)
        if config is None:
            self.notify(f"Connection '{connection_name}' not found", severity="warning")
            return

        self._apply_history_query(query)

        if (
            self.current_connection is not None
            and self.current_config is not None
            and self.current_config.name == connection_name
        ):
            self._pending_telescope_query = None
            return

        self._pending_telescope_query = None
        self._connect_like_explorer(connection_name, config)

    def _get_telescope_connection_map(self: QueryMixinHost) -> dict[str, Any]:
        connection_map = {config.name: config for config in getattr(self, "connections", [])}
        for config in (
            getattr(self, "_direct_connection_config", None),
            getattr(self, "current_config", None),
        ):
            if config and config.name not in connection_map:
                connection_map[config.name] = config
        return connection_map

    def _connect_like_explorer(self: QueryMixinHost, connection_name: str, config: Any) -> None:
        node = None
        object_tree = getattr(self, "object_tree", None)
        if object_tree is not None:
            try:
                stack = [object_tree.root]
                while stack:
                    current = stack.pop()
                    for child in current.children:
                        if getattr(self, "_get_node_kind", None) and self._get_node_kind(child) != "connection":
                            stack.append(child)
                            continue
                        data = getattr(child, "data", None)
                        node_config = getattr(data, "config", None)
                        if node_config and node_config.name == connection_name:
                            node = child
                            stack = []
                            break
                        stack.append(child)
            except Exception:
                node = None

        if node is not None and hasattr(self, "_activate_tree_node"):
            self._activate_tree_node(node)
            return

        self.connect_to_server(config)

    def _format_telescope_connection_label(self: QueryMixinHost, config: Any) -> str:
        endpoint = getattr(config, "tcp_endpoint", None)
        if endpoint is None:
            file_endpoint = getattr(config, "file_endpoint", None)
            if file_endpoint and getattr(file_endpoint, "path", ""):
                return file_endpoint.path
            return getattr(config, "name", "")
        database = getattr(config, "database", "")
        return database or getattr(config, "name", "")

    def _load_starred_by_connection(self: QueryMixinHost, connection_map: dict[str, Any]) -> dict[str, set[str]]:
        starred_store = self.services.starred_store
        loader = getattr(starred_store, "load_all", None)
        if callable(loader):
            return loader()
        return {
            name: starred_store.load_for_connection(name)
            for name in connection_map.keys()
        }

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
