"""Query execution mixin for SSMSTUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pyarrow as pa
from rich.markup import escape as escape_markup
from textual.worker import Worker
from textual_fastdatatable import ArrowBackend

from sqlit.domains.query.editing import deletion as edit_delete
from sqlit.shared.ui.protocols import QueryMixinHost
from sqlit.shared.ui.spinner import Spinner
from sqlit.shared.ui.widgets import SqlitDataTable
from sqlit.shared.core.utils import format_duration_ms

if TYPE_CHECKING:
    from sqlit.domains.query.app.query_service import QueryService

# Row limits for rendering
MAX_FETCH_ROWS = 100000
MAX_RENDER_ROWS = 100000

# Column content truncation (full value shown in tooltip and copied to clipboard)
MAX_COLUMN_CONTENT_WIDTH = 100


class QueryMixin:
    """Mixin providing query execution functionality.

    Attributes:
        _query_service: Optional QueryService instance.
            Set this in tests to inject a mock query service.
    """

    _query_service: QueryService | None = None
    _history_store: Any | None = None
    _query_service_db_type: str | None = None

    _query_worker: Worker[Any] | None = None
    _schema_worker: Worker[Any] | None = None
    _cancellable_query: Any | None = None
    _query_spinner: Spinner | None = None
    _query_cursor_cache: dict[str, tuple[int, int]] | None = None  # query text -> cursor (row, col)
    _results_table_counter: int = 0  # Counter for unique table IDs
    _query_target_database: str | None = None

    def action_execute_query(self: QueryMixinHost) -> None:
        """Execute the current query."""
        self._execute_query_common(keep_insert_mode=False)

    def action_execute_query_insert(self: QueryMixinHost) -> None:
        """Execute query in INSERT mode without leaving it."""
        self._execute_query_common(keep_insert_mode=True)

    def action_copy_query(self: QueryMixinHost) -> None:
        """Copy the current query to clipboard."""
        from sqlit.shared.ui.widgets import flash_widget

        query = self.query_input.text.strip()
        if not query:
            self.notify("Query is empty", severity="warning")
            return
        self._copy_text(query)
        flash_widget(self.query_input)

    def action_copy_context(self: QueryMixinHost) -> None:
        """Copy based on current focus (query or results)."""
        if self.query_input.has_focus:
            self.action_copy_query()
            return
        if self.results_table.has_focus:
            self.action_copy_cell()
            return
        self.notify("Nothing to copy", severity="warning")

    def action_delete_line(self: QueryMixinHost) -> None:
        """Delete the current line in the query editor."""
        self._clear_leader_pending()
        result = edit_delete.delete_line(
            self.query_input.text,
            *self.query_input.cursor_location,
        )
        self._apply_edit_result(result)

    def action_delete_word(self: QueryMixinHost) -> None:
        """Delete forward word starting at cursor."""
        self._clear_leader_pending()
        result = edit_delete.delete_word(
            self.query_input.text,
            *self.query_input.cursor_location,
        )
        self._apply_edit_result(result)

    def action_delete_word_back(self: QueryMixinHost) -> None:
        """Delete word backwards from cursor."""
        self._clear_leader_pending()
        result = edit_delete.delete_word_back(
            self.query_input.text,
            *self.query_input.cursor_location,
        )
        self._apply_edit_result(result)

    def action_delete_word_end(self: QueryMixinHost) -> None:
        """Delete through the end of the current word."""
        self._clear_leader_pending()
        result = edit_delete.delete_word_end(
            self.query_input.text,
            *self.query_input.cursor_location,
        )
        self._apply_edit_result(result)

    def action_delete_line_start(self: QueryMixinHost) -> None:
        """Delete from line start to cursor."""
        self._clear_leader_pending()
        result = edit_delete.delete_line_start(
            self.query_input.text,
            *self.query_input.cursor_location,
        )
        self._apply_edit_result(result)

    def action_delete_line_end(self: QueryMixinHost) -> None:
        """Delete from cursor to line end."""
        self._clear_leader_pending()
        result = edit_delete.delete_line_end(
            self.query_input.text,
            *self.query_input.cursor_location,
        )
        self._apply_edit_result(result)

    def action_delete_char(self: QueryMixinHost) -> None:
        """Delete the character under the cursor."""
        self._clear_leader_pending()
        result = edit_delete.delete_char(
            self.query_input.text,
            *self.query_input.cursor_location,
        )
        self._apply_edit_result(result)

    def action_delete_char_back(self: QueryMixinHost) -> None:
        """Delete the character before the cursor."""
        self._clear_leader_pending()
        result = edit_delete.delete_char_back(
            self.query_input.text,
            *self.query_input.cursor_location,
        )
        self._apply_edit_result(result)

    def action_delete_to_end(self: QueryMixinHost) -> None:
        """Delete from cursor to end of buffer."""
        self._clear_leader_pending()
        result = edit_delete.delete_to_end(
            self.query_input.text,
            *self.query_input.cursor_location,
        )
        self._apply_edit_result(result)

    def action_delete_all(self: QueryMixinHost) -> None:
        """Delete all query text."""
        self._clear_leader_pending()
        result = edit_delete.delete_all(
            self.query_input.text,
            *self.query_input.cursor_location,
        )
        self._apply_edit_result(result)

    # ========================================================================
    # New vim motion delete actions
    # ========================================================================

    def action_delete_WORD(self: QueryMixinHost) -> None:
        """Delete WORD (whitespace-delimited) forward."""
        self._clear_leader_pending()
        self._delete_with_motion("W")

    def action_delete_WORD_back(self: QueryMixinHost) -> None:
        """Delete WORD backward."""
        self._clear_leader_pending()
        self._delete_with_motion("B")

    def action_delete_WORD_end(self: QueryMixinHost) -> None:
        """Delete to WORD end."""
        self._clear_leader_pending()
        self._delete_with_motion("E")

    def action_delete_left(self: QueryMixinHost) -> None:
        """Delete character to the left (like backspace)."""
        self._clear_leader_pending()
        self._delete_with_motion("h")

    def action_delete_right(self: QueryMixinHost) -> None:
        """Delete character to the right."""
        self._clear_leader_pending()
        self._delete_with_motion("l")

    def action_delete_up(self: QueryMixinHost) -> None:
        """Delete current and previous line."""
        self._clear_leader_pending()
        self._delete_with_motion("k")

    def action_delete_down(self: QueryMixinHost) -> None:
        """Delete current and next line."""
        self._clear_leader_pending()
        self._delete_with_motion("j")

    def action_delete_line_end_motion(self: QueryMixinHost) -> None:
        """Delete to end of line ($ motion)."""
        self._clear_leader_pending()
        self._delete_with_motion("$")

    def action_delete_matching_bracket(self: QueryMixinHost) -> None:
        """Delete to matching bracket."""
        self._clear_leader_pending()
        self._delete_with_motion("%")

    def action_delete_find_char(self: QueryMixinHost) -> None:
        """Start delete to char (f motion) - shows menu for char input."""
        self._clear_leader_pending()
        self._show_char_pending_menu("f")

    def action_delete_find_char_back(self: QueryMixinHost) -> None:
        """Start delete back to char (F motion) - shows menu for char input."""
        self._clear_leader_pending()
        self._show_char_pending_menu("F")

    def action_delete_till_char(self: QueryMixinHost) -> None:
        """Start delete till char (t motion) - shows menu for char input."""
        self._clear_leader_pending()
        self._show_char_pending_menu("t")

    def action_delete_till_char_back(self: QueryMixinHost) -> None:
        """Start delete back till char (T motion) - shows menu for char input."""
        self._clear_leader_pending()
        self._show_char_pending_menu("T")

    def action_delete_inner(self: QueryMixinHost) -> None:
        """Start delete inside text object - shows menu for object selection."""
        self._clear_leader_pending()
        self._show_text_object_menu("inner")

    def action_delete_around(self: QueryMixinHost) -> None:
        """Start delete around text object - shows menu for object selection."""
        self._clear_leader_pending()
        self._show_text_object_menu("around")

    def _show_char_pending_menu(self: QueryMixinHost, motion: str) -> None:
        """Show the char pending menu and handle the result."""
        from sqlit.domains.query.ui.screens import CharPendingMenuScreen

        def handle_result(char: str | None) -> None:
            if char:
                self._delete_with_motion(motion, char)

        self.push_screen(CharPendingMenuScreen(motion), handle_result)

    def _show_text_object_menu(self: QueryMixinHost, mode: str) -> None:
        """Show the text object menu and handle the result."""
        from sqlit.domains.query.ui.screens import TextObjectMenuScreen

        def handle_result(obj_char: str | None) -> None:
            if obj_char:
                around = mode == "around"
                self._delete_with_text_object(obj_char, around)

        self.push_screen(TextObjectMenuScreen(mode), handle_result)

    def _delete_with_motion(self: QueryMixinHost, motion_key: str, char: str | None = None) -> None:
        """Execute delete with a motion."""
        from sqlit.domains.query.editing import MOTIONS, operator_delete

        motion_func = MOTIONS.get(motion_key)
        if not motion_func:
            return

        text = self.query_input.text
        row, col = self.query_input.cursor_location

        result = motion_func(text, row, col, char)
        if not result.range:
            return

        # Push undo state before delete
        self._push_undo_state()

        op_result = operator_delete(text, result.range)
        self.query_input.text = op_result.text
        self.query_input.cursor_location = (op_result.row, op_result.col)

        # Copy deleted text to system clipboard
        if op_result.yanked:
            self._copy_text(op_result.yanked)

    def _delete_with_text_object(self: QueryMixinHost, obj_char: str, around: bool) -> None:
        """Execute delete with a text object."""
        from sqlit.domains.query.editing import get_text_object, operator_delete

        text = self.query_input.text
        row, col = self.query_input.cursor_location

        range_obj = get_text_object(obj_char, text, row, col, around)
        if not range_obj:
            return

        # Push undo state before delete
        self._push_undo_state()

        op_result = operator_delete(text, range_obj)
        self.query_input.text = op_result.text
        self.query_input.cursor_location = (op_result.row, op_result.col)

        # Copy deleted text to system clipboard
        if op_result.yanked:
            self._copy_text(op_result.yanked)

    def _clear_leader_pending(self: QueryMixinHost) -> None:
        """Clear any leader pending state if supported by the host."""
        cancel = getattr(self, "_cancel_leader_pending", None)
        if callable(cancel):
            cancel()

    def _apply_edit_result(self: QueryMixinHost, result: edit_delete.EditResult) -> None:
        # Push undo state before applying changes
        self._push_undo_state()
        self.query_input.text = result.text
        self.query_input.cursor_location = (max(0, result.row), max(0, result.col))

    # ========================================================================
    # Clipboard actions (CTRL+A/C/V)
    # ========================================================================

    def action_select_all(self: QueryMixinHost) -> None:
        """Select all text in query editor (CTRL+A)."""
        from textual.widgets.text_area import Selection

        from sqlit.domains.query.editing import select_all_range

        text = self.query_input.text
        if not text:
            return

        start_row, start_col, end_row, end_col = select_all_range(text)
        # TextArea selection requires a Selection object
        self.query_input.selection = Selection(
            (start_row, start_col), (end_row, end_col)
        )

    def action_copy_selection(self: QueryMixinHost) -> None:
        """Copy selected text to clipboard (CTRL+C)."""
        from sqlit.domains.query.editing import get_selection_text
        from sqlit.shared.ui.widgets import flash_widget

        selection = self.query_input.selection
        # Check if there's an actual selection (start != end)
        if selection.start == selection.end:
            # No selection, copy current line or do nothing
            return

        start_row, start_col = selection.start
        end_row, end_col = selection.end

        text = get_selection_text(
            self.query_input.text,
            start_row,
            start_col,
            end_row,
            end_col,
        )

        if text:
            self._copy_text(text)
            flash_widget(self.query_input)

    def action_paste(self: QueryMixinHost) -> None:
        """Paste text from clipboard (CTRL+V)."""
        from textual.widgets.text_area import Selection

        from sqlit.domains.query.editing import paste_text

        clipboard = self._get_clipboard_text()
        if not clipboard:
            return

        # Push undo state before paste
        self._push_undo_state()

        text = self.query_input.text
        row, col = self.query_input.cursor_location

        # If there's a selection, delete it first
        selection = self.query_input.selection
        if selection.start != selection.end:
            start = selection.start
            end = selection.end
            # Order the selection
            if start > end:
                start, end = end, start
            # Delete selection by replacing with paste content
            from sqlit.domains.query.editing.types import MotionType, Position, Range
            from sqlit.domains.query.editing import operator_delete

            range_obj = Range(
                Position(start[0], start[1]),
                Position(end[0], end[1]),
                MotionType.CHARWISE,
                inclusive=False,
            )
            result = operator_delete(text, range_obj)
            text = result.text
            row, col = result.row, result.col

        paste_result = paste_text(text, row, col, clipboard)
        self.query_input.text = paste_result.text
        self.query_input.cursor_location = (paste_result.row, paste_result.col)
        # Clear selection by setting cursor position (start == end)
        cursor = self.query_input.cursor_location
        self.query_input.selection = Selection(cursor, cursor)

    def _get_clipboard_text(self: QueryMixinHost) -> str:
        """Get text from system clipboard."""
        try:
            import pyperclip
            return pyperclip.paste() or ""
        except Exception:
            return ""

    # ========================================================================
    # Undo/Redo actions
    # ========================================================================

    def _get_undo_history(self: QueryMixinHost) -> Any:
        """Get or create the undo history instance."""
        from sqlit.domains.query.editing import UndoHistory

        if self._undo_history is None:
            self._undo_history = UndoHistory()
        return self._undo_history

    def _push_undo_state(self: QueryMixinHost) -> None:
        """Push current state to undo history."""
        history = self._get_undo_history()
        text = self.query_input.text
        row, col = self.query_input.cursor_location
        history.push(text, row, col)

    def action_undo(self: QueryMixinHost) -> None:
        """Undo the last edit."""
        history = self._get_undo_history()
        if not history.can_undo():
            return

        state = history.undo()
        if state:
            self.query_input.text = state.text
            self.query_input.cursor_location = (state.cursor_row, state.cursor_col)

    def action_redo(self: QueryMixinHost) -> None:
        """Redo the last undone edit."""
        history = self._get_undo_history()
        if not history.can_redo():
            return

        state = history.redo()
        if state:
            self.query_input.text = state.text
            self.query_input.cursor_location = (state.cursor_row, state.cursor_col)

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
        from sqlit.domains.query.app.query_service import QueryResult, QueryService
        from sqlit.domains.query.app.query_service import parse_use_statement

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

    def _replace_results_table(self: QueryMixinHost, columns: list[str], rows: list[tuple]) -> None:
        """Update the results table with new data.

        Creates a new FastDataTable with ArrowBackend.
        """
        container = self.results_area
        old_table = self.results_table

        # Generate unique ID for new table
        self._results_table_counter += 1
        new_id = f"results-table-{self._results_table_counter}"

        if not columns:
            # No columns at all - create empty table with no header
            new_table = SqlitDataTable(id=new_id, zebra_stripes=True, show_header=False)
            container.mount(new_table, after=old_table)
            old_table.remove()
            return

        if not rows:
            # Columns but no rows - show headers with empty table
            empty_columns: dict[str, list[Any]] = {col: [] for col in columns}
            arrow_table = pa.table(empty_columns)
            backend = ArrowBackend(arrow_table)
            new_table = SqlitDataTable(
                id=new_id,
                zebra_stripes=True,
                backend=backend,
                max_column_content_width=MAX_COLUMN_CONTENT_WIDTH,
            )
            container.mount(new_table, after=old_table)
            old_table.remove()
            return

        # Prepare data (escape markup and handle NULL)
        formatted_rows = []
        for row in rows[:MAX_RENDER_ROWS]:
            formatted = []
            for i in range(len(columns)):
                val = row[i] if i < len(row) else None
                str_val = escape_markup(str(val)) if val is not None else "NULL"
                formatted.append(str_val)
            formatted_rows.append(formatted)

        # Build Arrow table
        formatted_columns: dict[str, list[Any]] = {
            col: [r[i] for r in formatted_rows] for i, col in enumerate(columns)
        }
        arrow_table = pa.table(formatted_columns)
        backend = ArrowBackend(arrow_table)

        # Create and mount new table, then remove old
        new_table = SqlitDataTable(
            id=new_id,
            zebra_stripes=True,
            backend=backend,
            max_column_content_width=MAX_COLUMN_CONTENT_WIDTH,
        )
        container.mount(new_table, after=old_table)
        old_table.remove()

    def _replace_results_table_raw(self: QueryMixinHost, columns: list[str], rows: list[tuple]) -> None:
        """Update the results table with pre-formatted data (no escaping).

        Use this when the data is already escaped/formatted (e.g., with highlighting).
        """
        container = self.results_area
        old_table = self.results_table

        # Generate unique ID for new table
        self._results_table_counter += 1
        new_id = f"results-table-{self._results_table_counter}"

        if not columns:
            # No columns at all - create empty table with no header
            new_table = SqlitDataTable(id=new_id, zebra_stripes=True, show_header=False)
            container.mount(new_table, after=old_table)
            old_table.remove()
            return

        if not rows:
            # Columns but no rows - show headers with empty table
            empty_columns: dict[str, list[Any]] = {col: [] for col in columns}
            arrow_table = pa.table(empty_columns)
            backend = ArrowBackend(arrow_table)
            new_table = SqlitDataTable(
                id=new_id,
                zebra_stripes=True,
                backend=backend,
                max_column_content_width=MAX_COLUMN_CONTENT_WIDTH,
            )
            container.mount(new_table, after=old_table)
            old_table.remove()
            return

        # Build Arrow table (data is already formatted)
        raw_columns: dict[str, list[Any]] = {}
        for i, col in enumerate(columns):
            raw_columns[col] = [r[i] for r in rows[:MAX_RENDER_ROWS]]
        arrow_table = pa.table(raw_columns)
        backend = ArrowBackend(arrow_table)

        # Create and mount new table, then remove old
        new_table = SqlitDataTable(
            id=new_id,
            zebra_stripes=True,
            backend=backend,
            max_column_content_width=MAX_COLUMN_CONTENT_WIDTH,
        )
        container.mount(new_table, after=old_table)
        old_table.remove()

    def _display_query_results(
        self: QueryMixinHost, columns: list[str], rows: list[tuple], row_count: int, truncated: bool, elapsed_ms: float
    ) -> None:
        """Display query results in the results table (called on main thread)."""
        self._last_result_columns = columns
        self._last_result_rows = rows
        self._last_result_row_count = row_count

        self._replace_results_table(columns, rows)

        time_str = format_duration_ms(elapsed_ms)
        if truncated:
            self.notify(f"Query returned {row_count}+ rows in {time_str} (truncated)", severity="warning")
        else:
            self.notify(f"Query returned {row_count} rows in {time_str}")

    def _display_non_query_result(self: QueryMixinHost, affected: int, elapsed_ms: float) -> None:
        """Display non-query result (called on main thread)."""
        self._last_result_columns = ["Result"]
        self._last_result_rows = [(f"{affected} row(s) affected",)]
        self._last_result_row_count = 1

        self._replace_results_table(["Result"], [(f"{affected} row(s) affected",)])
        time_str = format_duration_ms(elapsed_ms)
        self.notify(f"Query executed: {affected} row(s) affected in {time_str}")

    def _display_query_error(self: QueryMixinHost, error_message: str) -> None:
        """Display query error (called on main thread)."""
        # notify(severity="error") handles displaying the error in results via _show_error_in_results
        self.notify(f"Query error: {error_message}", severity="error")

    def _restore_insert_mode(self: QueryMixinHost) -> None:
        """Restore INSERT mode after query execution (called on main thread)."""
        from sqlit.shared.ui.widgets import VimMode

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
