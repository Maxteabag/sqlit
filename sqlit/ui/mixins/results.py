"""Results handling mixin for SSMSTUI."""

from __future__ import annotations

from ...widgets import SqlitDataTable

from ..protocols import AppProtocol


class ResultsMixin:
    """Mixin providing results handling functionality."""

    def _copy_text(self: AppProtocol, text: str) -> bool:
        """Copy text to clipboard if possible, otherwise store internally."""
        self._internal_clipboard = text

        # Prefer Textual's clipboard support (OSC52 where available).
        try:
            self.copy_to_clipboard(text)
            return True
        except Exception:
            pass

        # Fallback to system clipboard via pyperclip (requires platform support).
        try:
            import pyperclip  # noqa: F401  # type: ignore

            pyperclip.copy(text)
            return True
        except Exception:
            return False

    def _flash_table_yank(self: AppProtocol, table: SqlitDataTable, scope: str) -> None:
        """Briefly flash the yanked cell(s) to confirm a copy action."""
        from ...widgets import flash_widget

        previous_cursor_type = getattr(table, "cursor_type", "cell")
        css_class = "flash-cell"
        target_cursor_type: str = "cell"

        if scope == "row":
            css_class = "flash-row"
            target_cursor_type = "row"
        elif scope == "all":
            css_class = "flash-all"
            target_cursor_type = previous_cursor_type

        try:
            table.cursor_type = target_cursor_type  # type: ignore[assignment]
        except Exception:
            pass

        def restore_cursor() -> None:
            try:
                table.cursor_type = previous_cursor_type  # type: ignore[assignment]
            except Exception:
                pass

        flash_widget(table, css_class, on_complete=restore_cursor)

    def _format_tsv(self, columns: list[str], rows: list[tuple]) -> str:
        """Format columns and rows as TSV."""

        def fmt(value: object) -> str:
            if value is None:
                return "NULL"
            return str(value).replace("\t", " ").replace("\r", "").replace("\n", "\\n")

        lines: list[str] = []
        if columns:
            lines.append("\t".join(columns))
        for row in rows:
            lines.append("\t".join(fmt(v) for v in row))
        return "\n".join(lines)

    def action_view_cell(self: AppProtocol) -> None:
        """View the full value of the selected cell."""
        from ..screens import ValueViewScreen

        table = self.results_table
        if table.row_count <= 0:
            self.notify("No results", severity="warning")
            return
        try:
            value = table.get_cell_at(table.cursor_coordinate)
        except Exception:
            return
        self.push_screen(ValueViewScreen(str(value) if value is not None else "NULL", title="Cell Value"))

    def action_copy_cell(self: AppProtocol) -> None:
        """Copy the selected cell to clipboard (or internal clipboard)."""
        table = self.results_table
        if table.row_count <= 0:
            self.notify("No results", severity="warning")
            return
        try:
            value = table.get_cell_at(table.cursor_coordinate)
        except Exception:
            return
        self._copy_text(str(value) if value is not None else "NULL")
        self._flash_table_yank(table, "cell")

    def action_copy_row(self: AppProtocol) -> None:
        """Copy the selected row to clipboard (TSV)."""
        table = self.results_table
        if table.row_count <= 0:
            self.notify("No results", severity="warning")
            return
        try:
            row_values = table.get_row_at(table.cursor_row)
        except Exception:
            return

        text = self._format_tsv([], [tuple(row_values)])
        self._copy_text(text)
        self._flash_table_yank(table, "row")

    def action_copy_results(self: AppProtocol) -> None:
        """Copy the entire results (last query) to clipboard (TSV)."""
        if not self._last_result_columns and not self._last_result_rows:
            self.notify("No results", severity="warning")
            return

        text = self._format_tsv(self._last_result_columns, self._last_result_rows)
        self._copy_text(text)
        self._flash_table_yank(self.results_table, "all")

    def action_results_cursor_left(self: AppProtocol) -> None:
        """Move results cursor left (vim h)."""
        if self.results_table.has_focus:
            self.results_table.action_cursor_left()

    def action_results_cursor_down(self: AppProtocol) -> None:
        """Move results cursor down (vim j)."""
        if self.results_table.has_focus:
            self.results_table.action_cursor_down()

    def action_results_cursor_up(self: AppProtocol) -> None:
        """Move results cursor up (vim k)."""
        if self.results_table.has_focus:
            self.results_table.action_cursor_up()

    def action_results_cursor_right(self: AppProtocol) -> None:
        """Move results cursor right (vim l)."""
        if self.results_table.has_focus:
            self.results_table.action_cursor_right()

    def action_clear_results(self: AppProtocol) -> None:
        """Clear the results table."""
        self._replace_results_table([], [])  # type: ignore[attr-defined]
        self._last_result_columns = []
        self._last_result_rows = []
        self._last_result_row_count = 0

    def action_edit_cell(self: AppProtocol) -> None:
        """Generate an UPDATE query for the selected cell and enter insert mode."""
        table = self.results_table
        if table.row_count <= 0:
            self.notify("No results", severity="warning")
            return

        if not self._last_result_columns:
            self.notify("No column info", severity="warning")
            return

        try:
            cursor_row, cursor_col = table.cursor_coordinate
            value = table.get_cell_at(table.cursor_coordinate)
            row_values = table.get_row_at(cursor_row)
        except Exception:
            return

        # Get column name
        if cursor_col >= len(self._last_result_columns):
            return
        column_name = self._last_result_columns[cursor_col]

        # Check if this column is a primary key - don't allow editing PKs
        if hasattr(self, "_last_query_table") and self._last_query_table:
            for col in self._last_query_table.get("columns", []):
                if col.name == column_name and col.is_primary_key:
                    self.notify("Cannot edit primary key column", severity="warning")
                    return

        # Format value for SQL
        def sql_value(v: object) -> str:
            if v is None:
                return "NULL"
            if isinstance(v, bool):
                return "TRUE" if v else "FALSE"
            if isinstance(v, int | float):
                return str(v)
            # String - escape single quotes
            return "'" + str(v).replace("'", "''") + "'"

        # Get table name and primary key columns
        table_name = "<table>"
        pk_column_names: set[str] = set()

        if hasattr(self, "_last_query_table") and self._last_query_table:
            table_info = self._last_query_table
            table_name = table_info["name"]
            # Get PK columns from column info
            for col in table_info.get("columns", []):
                if col.is_primary_key:
                    pk_column_names.add(col.name)

        # Build WHERE clause - prefer PK columns, fall back to all columns
        where_parts = []
        for i, col in enumerate(self._last_result_columns):
            if i < len(row_values):
                # If we have PK info, only use PK columns; otherwise use all columns
                if pk_column_names and col not in pk_column_names:
                    continue
                val = row_values[i]
                if val is None:
                    where_parts.append(f"{col} IS NULL")
                else:
                    where_parts.append(f"{col} = {sql_value(val)}")

        # If no where parts (no PKs matched result columns), fall back to all columns
        if not where_parts:
            for i, col in enumerate(self._last_result_columns):
                if i < len(row_values):
                    val = row_values[i]
                    if val is None:
                        where_parts.append(f"{col} IS NULL")
                    else:
                        where_parts.append(f"{col} = {sql_value(val)}")

        where_clause = " AND ".join(where_parts)

        # Generate UPDATE query with empty placeholder for the new value
        query = f"UPDATE {table_name} SET {column_name} = '' WHERE {where_clause};"

        # Find position inside the empty quotes (after "SET column = '")
        set_prefix = f"SET {column_name} = '"
        cursor_pos = query.find(set_prefix) + len(set_prefix)

        # Set query and switch to insert mode
        self.query_input.text = query
        self.query_input.focus()

        # Position cursor inside the empty quotes
        self.query_input.cursor_location = (0, cursor_pos)

        # Enter insert mode
        from ...widgets import VimMode
        self.vim_mode = VimMode.INSERT
        self.query_input.read_only = False
        self._update_status_bar()
        self._update_footer_bindings()
