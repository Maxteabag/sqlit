"""Results handling mixin for SSMSTUI."""

from __future__ import annotations

from textual.widgets import DataTable

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

    def _flash_table_yank(self: AppProtocol, table: DataTable, scope: str) -> None:
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
