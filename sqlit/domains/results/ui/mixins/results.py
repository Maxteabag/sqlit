"""Results handling mixin for SSMSTUI."""

from __future__ import annotations

import sys
from typing import Any

from sqlit.shared.ui.protocols import ResultsMixinHost
from sqlit.shared.ui.widgets import SqlitDataTable

MIN_TIMER_DELAY_S = 0.001


class ResultsMixin:
    """Mixin providing results handling functionality."""

    _last_result_columns: list[str] = []
    _last_result_rows: list[tuple[Any, ...]] = []
    _last_result_row_count: int = 0
    _tooltip_cell_coord: tuple[int, int] | None = None
    _tooltip_showing: bool = False
    _tooltip_timer: Any | None = None

    def _schedule_results_timer(self: ResultsMixinHost, delay_s: float, callback: Any) -> Any | None:
        set_timer = getattr(self, "set_timer", None)
        if callable(set_timer):
            return set_timer(delay_s, callback)
        call_later = getattr(self, "call_later", None)
        if callable(call_later):
            try:
                call_later(callback)
                return None
            except Exception:
                pass
        try:
            callback()
        except Exception:
            pass
        return None

    def _apply_result_table_columns(
        self: ResultsMixinHost,
        table_info: dict[str, Any],
        token: int,
        columns: list[Any],
    ) -> None:
        if table_info.get("_columns_token") != token:
            return
        table_info["columns"] = columns

    def _prime_result_table_columns(self: ResultsMixinHost, table_info: dict[str, Any] | None) -> None:
        if not table_info:
            return
        if table_info.get("columns"):
            return
        name = table_info.get("name")
        if not name:
            return
        database = table_info.get("database")
        schema = table_info.get("schema")
        token = int(table_info.get("_columns_token", 0)) + 1
        table_info["_columns_token"] = token

        async def work_async() -> None:
            import asyncio

            columns: list[Any] = []
            try:
                runtime = getattr(self.services, "runtime", None)
                use_worker = bool(getattr(runtime, "process_worker", False)) and not bool(
                    getattr(getattr(runtime, "mock", None), "enabled", False)
                )
                client = None
                if use_worker and hasattr(self, "_get_process_worker_client_async"):
                    client = await self._get_process_worker_client_async()  # type: ignore[attr-defined]

                if client is not None and hasattr(client, "list_columns") and self.current_config is not None:
                    outcome = await asyncio.to_thread(
                        client.list_columns,
                        config=self.current_config,
                        database=database,
                        schema=schema,
                        name=name,
                    )
                    if getattr(outcome, "cancelled", False):
                        return
                    error = getattr(outcome, "error", None)
                    if error:
                        raise RuntimeError(error)
                    columns = outcome.columns or []
                else:
                    schema_service = getattr(self, "_get_schema_service", None)
                    if callable(schema_service):
                        service = self._get_schema_service()
                        if service:
                            columns = await asyncio.to_thread(
                                service.list_columns,
                                database,
                                schema,
                                name,
                            )
            except Exception:
                columns = []

            self._schedule_results_timer(
                MIN_TIMER_DELAY_S,
                lambda: self._apply_result_table_columns(table_info, token, columns),
            )

        self.run_worker(work_async(), name=f"prime-result-columns-{name}", exclusive=False)

    def _normalize_column_name(self: ResultsMixinHost, name: str) -> str:
        trimmed = name.strip()
        if len(trimmed) >= 2:
            if trimmed[0] == trimmed[-1] and trimmed[0] in ("\"", "`"):
                trimmed = trimmed[1:-1]
            elif trimmed[0] == "[" and trimmed[-1] == "]":
                trimmed = trimmed[1:-1]
        if "." in trimmed and not any(q in trimmed for q in ("\"", "`", "[")):
            trimmed = trimmed.split(".")[-1]
        return trimmed.lower()

    def _get_active_results_table_info(
        self: ResultsMixinHost,
        table: SqlitDataTable | None,
        stacked: bool,
    ) -> dict[str, Any] | None:
        if not table:
            return None
        if stacked:
            section = self._find_results_section(table)
            table_info = getattr(section, "result_table_info", None)
            if table_info:
                return table_info
        table_info = getattr(table, "result_table_info", None)
        if table_info:
            return table_info
        return getattr(self, "_last_query_table", None)

    def _copy_text(self: ResultsMixinHost, text: str) -> bool:
        """Copy text to clipboard if possible, otherwise store internally."""
        self._internal_clipboard = text

        if sys.platform == "darwin":
            # Prefer pyperclip on macOS; Textual's copy_to_clipboard can no-op.
            try:
                import pyperclip  # type: ignore

                pyperclip.copy(text)
                return True
            except Exception:
                pass

        # Prefer Textual's clipboard support (OSC52 where available).
        try:
            self.copy_to_clipboard(text)
            return True
        except Exception:
            pass

        # Fallback to system clipboard via pyperclip (requires platform support).
        try:
            import pyperclip  # type: ignore

            pyperclip.copy(text)
            return True
        except Exception:
            return False

    def _get_active_results_context(
        self: ResultsMixinHost,
    ) -> tuple[SqlitDataTable | None, list[str], list[tuple], bool]:
        """Get the active results table and data, handling stacked mode."""
        if self.results_area.has_class("stacked-mode"):
            try:
                from sqlit.shared.ui.widgets_stacked_results import ResultSection, StackedResultsContainer

                container = self.query_one("#stacked-results", StackedResultsContainer)
                focused_table = next(
                    (table for table in container.query(SqlitDataTable) if table.has_focus),
                    None,
                )
                section = None
                table = None

                if focused_table is not None:
                    table = focused_table
                    section = self._find_results_section(table)
                else:
                    sections = list(container.query(ResultSection))
                    if not sections:
                        return None, [], [], True
                    section = next((s for s in sections if not s.collapsed), sections[0])
                    if section.collapsed:
                        section.collapsed = False
                        section.scroll_visible()
                    try:
                        table = section.query_one(SqlitDataTable)
                    except Exception:
                        table = None

                columns = list(getattr(section, "result_columns", [])) if section else []
                rows = list(getattr(section, "result_rows", [])) if section else []
                return table, columns, rows, True
            except Exception:
                return None, [], [], True
        return self.results_table, list(self._last_result_columns), list(self._last_result_rows), False

    def _find_results_section(self: ResultsMixinHost, widget: Any) -> Any | None:
        """Find the ResultSection ancestor for a widget."""
        from sqlit.shared.ui.widgets_stacked_results import ResultSection

        current = widget
        while current is not None:
            if isinstance(current, ResultSection):
                return current
            current = getattr(current, "parent", None)
        return None

    def _flash_table_yank(self: ResultsMixinHost, table: SqlitDataTable, scope: str) -> None:
        """Briefly flash the yanked cell(s) to confirm a copy action."""
        from sqlit.shared.ui.widgets import flash_widget

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

    def action_view_cell(self: ResultsMixinHost) -> None:
        """Preview the selected cell value (tooltip)."""
        table, _columns, _rows, _stacked = self._get_active_results_context()
        if not table or table.row_count <= 0:
            self.notify("No results", severity="warning")
            return
        try:
            cursor_coord = table.cursor_coordinate
            value = table.get_cell_at(cursor_coord)
        except Exception:
            return

        coord_key = (
            (cursor_coord.row, cursor_coord.column)
            if hasattr(cursor_coord, "row")
            else tuple(cursor_coord)
        )

        if self._tooltip_showing and self._tooltip_cell_coord == coord_key:
            self._hide_cell_tooltip(table)
            return

        self._show_cell_tooltip(table, cursor_coord, value)

    def action_view_cell_full(self: ResultsMixinHost) -> None:
        """View the full value of the selected cell inline."""
        from sqlit.shared.ui.widgets import InlineValueView

        table, _columns, _rows, _stacked = self._get_active_results_context()
        if not table or table.row_count <= 0:
            self.notify("No results", severity="warning")
            return
        try:
            _cursor_row, cursor_col = table.cursor_coordinate
            value = table.get_cell_at(table.cursor_coordinate)
        except Exception:
            return

        self._hide_cell_tooltip(table)

        # Get column name if available
        column_name = ""
        if self._last_result_columns and cursor_col < len(self._last_result_columns):
            column_name = self._last_result_columns[cursor_col]

        # Show inline value view
        try:
            value_view = self.query_one("#value-view", InlineValueView)
            value_view.set_value(str(value) if value is not None else "NULL", column_name)
            value_view.show()
            if hasattr(self, "_value_view_active"):
                self._value_view_active = True
        except Exception:
            pass

    def action_close_value_view(self: ResultsMixinHost) -> None:
        """Close the inline value view and return to results table."""
        from sqlit.shared.ui.widgets import InlineValueView

        try:
            value_view = self.query_one("#value-view", InlineValueView)
            if value_view.is_visible:
                value_view.hide()
                table, _columns, _rows, _stacked = self._get_active_results_context()
                if table:
                    table.focus()
                if hasattr(self, "_value_view_active"):
                    self._value_view_active = False
        except Exception:
            pass

    def action_copy_value_view(self: ResultsMixinHost) -> None:
        """Copy the value from the inline value view.

        In tree mode with JSON, opens the vy yank menu.
        In syntax mode, copies the full value directly.
        """
        from sqlit.shared.ui.widgets import InlineValueView, flash_widget

        try:
            value_view = self.query_one("#value-view", InlineValueView)
            if not value_view.is_visible:
                return
            # In tree mode with JSON, open the yank menu
            if value_view._is_json and value_view._tree_mode:
                self._start_leader_pending("vy")
                return
            # In syntax mode, copy directly
            self._copy_text(value_view.value)
            flash_widget(value_view)
        except Exception:
            pass

    def action_vy_value(self: ResultsMixinHost) -> None:
        """Copy the current node's value (from yank menu)."""
        from sqlit.shared.ui.widgets import InlineValueView, flash_widget

        self._clear_leader_pending()
        try:
            value_view = self.query_one("#value-view", InlineValueView)
            if value_view.is_visible:
                text = value_view.get_cursor_value_json()
                if text:
                    self._copy_text(text)
                    tree = value_view.get_tree_widget()
                    if tree:
                        flash_widget(tree, "flash-cursor")
        except Exception:
            pass

    def action_vy_field(self: ResultsMixinHost) -> None:
        """Copy the current field as 'key': value (from yank menu)."""
        from sqlit.shared.ui.widgets import InlineValueView, flash_widget

        self._clear_leader_pending()
        try:
            value_view = self.query_one("#value-view", InlineValueView)
            if value_view.is_visible:
                text = value_view.get_cursor_field_json()
                if text:
                    self._copy_text(text)
                    tree = value_view.get_tree_widget()
                    if tree:
                        flash_widget(tree, "flash-cursor")
        except Exception:
            pass

    def action_vy_all(self: ResultsMixinHost) -> None:
        """Copy the full JSON (from yank menu)."""
        from sqlit.shared.ui.widgets import InlineValueView, flash_widget

        self._clear_leader_pending()
        try:
            value_view = self.query_one("#value-view", InlineValueView)
            if value_view.is_visible:
                self._copy_text(value_view.value)
                tree = value_view.get_tree_widget()
                if tree:
                    flash_widget(tree, "flash-all")
        except Exception:
            pass

    def action_toggle_value_view_mode(self: ResultsMixinHost) -> None:
        """Toggle between tree and syntax view in the inline value view."""
        from sqlit.shared.ui.widgets import InlineValueView

        try:
            value_view = self.query_one("#value-view", InlineValueView)
            if value_view.is_visible:
                value_view.toggle_view_mode()
                self._update_footer_bindings()
        except Exception:
            pass

    def action_collapse_all_json_nodes(self: ResultsMixinHost) -> None:
        """Collapse all nodes in the JSON tree view."""
        from sqlit.shared.ui.widgets import InlineValueView

        try:
            value_view = self.query_one("#value-view", InlineValueView)
            if value_view.is_visible:
                value_view.collapse_all_nodes()
        except Exception:
            pass

    def action_expand_all_json_nodes(self: ResultsMixinHost) -> None:
        """Expand all nodes in the JSON tree view."""
        from sqlit.shared.ui.widgets import InlineValueView

        try:
            value_view = self.query_one("#value-view", InlineValueView)
            if value_view.is_visible:
                value_view.expand_all_nodes()
        except Exception:
            pass

    def action_copy_cell(self: ResultsMixinHost) -> None:
        """Copy the selected cell to clipboard (or internal clipboard)."""
        table, _columns, _rows, _stacked = self._get_active_results_context()
        if not table or table.row_count <= 0:
            self.notify("No results", severity="warning")
            return
        try:
            value = table.get_cell_at(table.cursor_coordinate)
        except Exception:
            return
        self._copy_text(str(value) if value is not None else "NULL")
        self._flash_table_yank(table, "cell")

    def _show_cell_tooltip(
        self: ResultsMixinHost,
        table: SqlitDataTable,
        coordinate: Any,
        value: Any,
    ) -> None:
        """Show a manual tooltip preview for the selected cell."""
        if self._tooltip_timer is not None:
            self._tooltip_timer.stop()
            self._tooltip_timer = None

        tooltip_value = "NULL" if value is None else str(value)
        if len(tooltip_value) > 2000:
            tooltip_value = f"{tooltip_value[:2000]}..."

        try:
            table.tooltip = tooltip_value
            table._manual_tooltip_active = True
        except Exception:
            pass

        try:
            from textual.geometry import Offset

            cell_region = table._get_cell_region(coordinate)
            x = int(table.region.x + cell_region.x - int(table.scroll_x))
            y = int(table.region.y + cell_region.y - int(table.scroll_y))
            x += max(0, cell_region.width // 2)
            self.app.mouse_position = Offset(x, y)
        except Exception:
            pass

        try:
            screen = table.screen
            screen._tooltip_widget = table
            screen._handle_tooltip_timer(table)
        except Exception:
            pass

        coord_key = (
            (coordinate.row, coordinate.column)
            if hasattr(coordinate, "row")
            else tuple(coordinate)
        )
        self._tooltip_cell_coord = coord_key
        self._tooltip_showing = True
        self._tooltip_timer = self.set_timer(2.5, lambda: self._hide_cell_tooltip(table))

    def _hide_cell_tooltip(self: ResultsMixinHost, table: SqlitDataTable) -> None:
        """Hide any active manual tooltip preview."""
        if self._tooltip_timer is not None:
            self._tooltip_timer.stop()
            self._tooltip_timer = None
        try:
            table.tooltip = None
            table._manual_tooltip_active = False
        except Exception:
            pass
        self._tooltip_cell_coord = None
        self._tooltip_showing = False

    def action_copy_row(self: ResultsMixinHost) -> None:
        """Copy the selected row to clipboard (TSV)."""
        table, _columns, _rows, _stacked = self._get_active_results_context()
        if not table or table.row_count <= 0:
            self.notify("No results", severity="warning")
            return
        try:
            row_values = table.get_row_at(table.cursor_row)
        except Exception:
            return

        text = self._format_tsv([], [tuple(row_values)])
        self._copy_text(text)
        self._flash_table_yank(table, "row")

    def action_copy_results(self: ResultsMixinHost) -> None:
        """Copy the entire results (last query) to clipboard (TSV)."""
        table, columns, rows, _stacked = self._get_active_results_context()
        if not columns and not rows:
            self.notify("No results", severity="warning")
            return

        text = self._format_tsv(columns, rows)
        self._copy_text(text)
        if table:
            self._flash_table_yank(table, "all")

    def action_results_yank_leader_key(self: ResultsMixinHost) -> None:
        """Open the results yank (copy) leader menu.

        If the result is an error message, copy it directly instead of showing the menu.
        """
        _table, columns, rows, _stacked = self._get_active_results_context()
        # If results show an error, copy it directly without showing the menu
        if columns == ["Error"] and rows:
            error_message = str(rows[0][0]) if rows[0] else ""
            self._copy_text(error_message)
            if _table:
                self._flash_table_yank(_table, "cell")
            return
        self._start_leader_pending("ry")

    def action_ry_cell(self: ResultsMixinHost) -> None:
        """Copy cell (from yank menu)."""
        self._clear_leader_pending()
        table, _columns, _rows, _stacked = self._get_active_results_context()
        if not table or table.row_count <= 0:
            self.notify("No results", severity="warning")
            return
        try:
            value = table.get_cell_at(table.cursor_coordinate)
        except Exception:
            return
        self._copy_text(str(value) if value is not None else "NULL")
        self._flash_table_yank(table, "cell")

    def action_ry_row(self: ResultsMixinHost) -> None:
        """Copy row (from yank menu)."""
        self._clear_leader_pending()
        table, _columns, _rows, _stacked = self._get_active_results_context()
        if not table or table.row_count <= 0:
            self.notify("No results", severity="warning")
            return
        try:
            row_values = table.get_row_at(table.cursor_row)
        except Exception:
            return
        text = self._format_tsv([], [tuple(row_values)])
        self._copy_text(text)
        self._flash_table_yank(table, "row")

    def action_ry_all(self: ResultsMixinHost) -> None:
        """Copy all results (from yank menu)."""
        self._clear_leader_pending()
        table, columns, rows, _stacked = self._get_active_results_context()
        if not columns and not rows:
            self.notify("No results", severity="warning")
            return
        text = self._format_tsv(columns, rows)
        self._copy_text(text)
        if table:
            self._flash_table_yank(table, "all")

    def action_ry_export(self: ResultsMixinHost) -> None:
        """Open the export submenu."""
        self._clear_leader_pending()
        self._start_leader_pending("rye")

    def action_rye_csv(self: ResultsMixinHost) -> None:
        """Export results as CSV to file."""
        self._clear_leader_pending()
        if not self._last_result_columns or not self._last_result_rows:
            self.notify("No results to export", severity="warning")
            return
        self._show_export_dialog("csv")

    def action_rye_json(self: ResultsMixinHost) -> None:
        """Export results as JSON to file."""
        self._clear_leader_pending()
        if not self._last_result_columns or not self._last_result_rows:
            self.notify("No results to export", severity="warning")
            return
        self._show_export_dialog("json")

    def _show_export_dialog(self: ResultsMixinHost, fmt: str) -> None:
        """Show the file save dialog for export."""
        from datetime import datetime

        from sqlit.shared.ui.screens.file_picker import FilePickerMode, FilePickerScreen

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = "csv" if fmt == "csv" else "json"
        default_filename = f"results_{timestamp}.{ext}"

        def handle_result(filename: str | None) -> None:
            if filename:
                self._save_export_file(filename, fmt)

        self.push_screen(
            FilePickerScreen(
                mode=FilePickerMode.SAVE,
                title="Export Results",
                default_filename=default_filename,
            ),
            handle_result,
        )

    def _save_export_file(self: ResultsMixinHost, filename: str, fmt: str) -> None:
        """Save the export file to disk."""
        from pathlib import Path

        from sqlit.domains.results.formatters import format_csv, format_json

        try:
            if fmt == "csv":
                content = format_csv(self._last_result_columns, self._last_result_rows)
            else:
                content = format_json(self._last_result_columns, self._last_result_rows)

            path = Path(filename).expanduser()
            path.write_text(content, encoding="utf-8")

            row_count = len(self._last_result_rows)
            self.notify(f"Saved {row_count} rows to {path.name}")
        except Exception as e:
            self.notify(f"Failed to save: {e}", severity="error")

    def action_results_cursor_left(self: ResultsMixinHost) -> None:
        """Move results cursor left (vim h)."""
        table, _columns, _rows, _stacked = self._get_active_results_context()
        if table and table.has_focus:
            table.action_cursor_left()

    def action_results_cursor_down(self: ResultsMixinHost) -> None:
        """Move results cursor down (vim j)."""
        table, _columns, _rows, _stacked = self._get_active_results_context()
        if table and table.has_focus:
            table.action_cursor_down()

    def action_results_cursor_up(self: ResultsMixinHost) -> None:
        """Move results cursor up (vim k)."""
        table, _columns, _rows, _stacked = self._get_active_results_context()
        if table and table.has_focus:
            table.action_cursor_up()

    def action_results_cursor_right(self: ResultsMixinHost) -> None:
        """Move results cursor right (vim l)."""
        table, _columns, _rows, _stacked = self._get_active_results_context()
        if table and table.has_focus:
            table.action_cursor_right()

    def action_clear_results(self: ResultsMixinHost) -> None:
        """Clear the results table."""
        if self.results_area.has_class("stacked-mode"):
            from sqlit.shared.ui.widgets_stacked_results import StackedResultsContainer

            try:
                container = self.query_one("#stacked-results", StackedResultsContainer)
                container.clear_results()
            except Exception:
                pass
            self._show_single_result_mode()
        self._replace_results_table([], [])
        self._last_result_columns = []
        self._last_result_rows = []
        self._last_result_row_count = 0

    def action_delete_row(self: ResultsMixinHost) -> None:
        """Generate a DELETE query for the selected row and enter insert mode."""
        table, columns, _rows, _stacked = self._get_active_results_context()
        if not table or table.row_count <= 0:
            self.notify("No results", severity="warning")
            return

        if not columns:
            self.notify("No column info", severity="warning")
            return

        try:
            cursor_row, _cursor_col = table.cursor_coordinate
            row_values = table.get_row_at(cursor_row)
        except Exception:
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
        table_info = self._get_active_results_table_info(table, _stacked)
        if table_info:
            table_name = table_info.get("name", table_name)
            # Get PK columns from column info
            for col in table_info.get("columns", []):
                if col.is_primary_key:
                    pk_column_names.add(self._normalize_column_name(col.name))

        # Build WHERE clause - prefer PK columns, fall back to all columns
        where_parts = []
        for i, col in enumerate(columns):
            if i < len(row_values):
                # If we have PK info, only use PK columns; otherwise use all columns
                if pk_column_names and self._normalize_column_name(col) not in pk_column_names:
                    continue
                val = row_values[i]
                if val is None:
                    where_parts.append(f"{col} IS NULL")
                else:
                    where_parts.append(f"{col} = {sql_value(val)}")

        # If no where parts (no PKs matched result columns), fall back to all columns
        if not where_parts:
            for i, col in enumerate(columns):
                if i < len(row_values):
                    val = row_values[i]
                    if val is None:
                        where_parts.append(f"{col} IS NULL")
                    else:
                        where_parts.append(f"{col} = {sql_value(val)}")

        if not where_parts:
            self.notify("No row values", severity="warning")
            return

        where_clause = " AND ".join(where_parts)

        # Generate DELETE query for the row
        query = f"DELETE FROM {table_name} WHERE {where_clause};"

        # Set query and switch to insert mode
        self._suppress_autocomplete_once = True
        self.query_input.text = query
        # Position cursor before the trailing semicolon
        cursor_pos = max(len(query) - 1, 0)
        self.query_input.cursor_location = (0, cursor_pos)

        # Focus query editor but keep NORMAL mode (no INSERT for deletes)
        self.action_focus_query()
        self._update_footer_bindings()

    def action_edit_cell(self: ResultsMixinHost) -> None:
        """Generate an UPDATE query for the selected cell and enter insert mode."""
        table, columns, _rows, _stacked = self._get_active_results_context()
        if not table or table.row_count <= 0:
            self.notify("No results", severity="warning")
            return

        if not columns:
            self.notify("No column info", severity="warning")
            return

        try:
            cursor_row, cursor_col = table.cursor_coordinate
            row_values = table.get_row_at(cursor_row)
        except Exception:
            return

        # Get column name
        if cursor_col >= len(columns):
            return
        column_name = columns[cursor_col]

        # Check if this column is a primary key - don't allow editing PKs
        table_info = self._get_active_results_table_info(table, _stacked)
        if table_info:
            for col in table_info.get("columns", []):
                if col.is_primary_key and self._normalize_column_name(col.name) == self._normalize_column_name(column_name):
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
        if table_info:
            table_name = table_info.get("name", table_name)
            # Get PK columns from column info
            for col in table_info.get("columns", []):
                if col.is_primary_key:
                    pk_column_names.add(self._normalize_column_name(col.name))

        # Build WHERE clause - prefer PK columns, fall back to all columns
        where_parts = []
        for i, col in enumerate(columns):
            if i < len(row_values):
                # If we have PK info, only use PK columns; otherwise use all columns
                if pk_column_names and self._normalize_column_name(col) not in pk_column_names:
                    continue
                val = row_values[i]
                if val is None:
                    where_parts.append(f"{col} IS NULL")
                else:
                    where_parts.append(f"{col} = {sql_value(val)}")

        # If no where parts (no PKs matched result columns), fall back to all columns
        if not where_parts:
            for i, col in enumerate(columns):
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
        self._suppress_autocomplete_once = True
        self.query_input.text = query
        self.query_input.focus()

        # Position cursor inside the empty quotes
        self.query_input.cursor_location = (0, cursor_pos)

        # Enter insert mode
        from sqlit.core.vim import VimMode
        self.vim_mode = VimMode.INSERT
        self.query_input.read_only = False
        self._update_vim_mode_visuals()
        self._update_footer_bindings()

    # Stacked results navigation

    def action_next_result_section(self: ResultsMixinHost) -> None:
        """Navigate to the next result section (for multi-statement results)."""
        from sqlit.shared.ui.widgets_stacked_results import ResultSection, StackedResultsContainer

        try:
            container = self.query_one("#stacked-results", StackedResultsContainer)
        except Exception:
            return

        if not container.has_class("active"):
            return

        sections = list(container.query(ResultSection))
        if not sections:
            return

        current_idx = next((i for i, section in enumerate(sections) if not section.collapsed), None)
        next_idx = 0 if current_idx is None else (current_idx + 1) % len(sections)

        if current_idx is not None:
            sections[current_idx].collapsed = True
        sections[next_idx].collapsed = False
        sections[next_idx].scroll_visible()
        self._focus_result_section(sections[next_idx])

    def action_prev_result_section(self: ResultsMixinHost) -> None:
        """Navigate to the previous result section (for multi-statement results)."""
        from sqlit.shared.ui.widgets_stacked_results import ResultSection, StackedResultsContainer

        try:
            container = self.query_one("#stacked-results", StackedResultsContainer)
        except Exception:
            return

        if not container.has_class("active"):
            return

        sections = list(container.query(ResultSection))
        if not sections:
            return

        current_idx = next((i for i, section in enumerate(sections) if not section.collapsed), None)
        prev_idx = (len(sections) - 1) if current_idx is None else (current_idx - 1) % len(sections)

        if current_idx is not None:
            sections[current_idx].collapsed = True
        sections[prev_idx].collapsed = False
        sections[prev_idx].scroll_visible()
        self._focus_result_section(sections[prev_idx])

    def action_toggle_result_section(self: ResultsMixinHost) -> None:
        """Toggle collapse/expand of the current result section."""
        from sqlit.shared.ui.widgets_stacked_results import ResultSection, StackedResultsContainer

        try:
            container = self.query_one("#stacked-results", StackedResultsContainer)
        except Exception:
            return

        if not container.has_class("active"):
            return

        sections = list(container.query(ResultSection))
        if not sections:
            return

        # Find the first non-collapsed section and toggle it
        for section in sections:
            if not section.collapsed:
                section.collapsed = True
                return

        # If all collapsed, expand the first one
        sections[0].collapsed = False
        self._focus_result_section(sections[0])

    def _focus_result_section(self: ResultsMixinHost, section: Any) -> None:
        """Focus the active result section content when possible."""
        try:
            table = section.query_one(SqlitDataTable)
            table.focus()
            return
        except Exception:
            pass
        try:
            section.focus()
        except Exception:
            pass
