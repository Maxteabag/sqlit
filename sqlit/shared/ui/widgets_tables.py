"""Table widgets for sqlit."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from rich.align import Align
from rich.errors import MarkupError
from rich.markup import escape
from rich.protocol import is_renderable
from rich.text import Text
from textual.coordinate import Coordinate

from textual.containers import Container
from textual.events import Key
from textual.strip import Strip
from textual_fastdatatable import DataTable as FastDataTable


class SqlitDataTable(FastDataTable):
    """FastDataTable with correct header behavior when show_header is False.

    Disables hover tooltips - use 'v' to view cell values.
    """

    # Track if a manual tooltip is being shown (via 'v' key)
    _manual_tooltip_active: bool = False

    def _set_tooltip_from_cell_at(self, coordinate: Any) -> None:
        """Override to disable hover tooltips entirely."""
        # Don't set tooltip on hover - we handle this manually via 'v' key
        pass

    def action_copy_selection(self) -> None:
        """Copy selection to clipboard, guarding against empty tables."""
        # Guard against empty table - the library doesn't check this
        if self.backend is None:
            return
        # Call parent implementation
        super().action_copy_selection()

    def render_line(self, y: int) -> Strip:
        width, _ = self.size
        scroll_x, scroll_y = self.scroll_offset

        fixed_rows_height = self.fixed_rows
        if self.show_header:
            fixed_rows_height += self.header_height

        if y >= fixed_rows_height:
            y += scroll_y

        if not self.show_header:
            # FastDataTable still renders the header row at y=0; offset by 1 when hidden.
            y += 1

        return self._render_line(y, scroll_x, scroll_x + width, self.rich_style)

    def _get_cell_renderable(self, row_index: int, column_index: int) -> Any:
        """Format cells with plain text for NULL/bool/date values."""
        if row_index == -1:
            return self.ordered_columns[column_index].label

        datum = self.get_cell_at(Coordinate(row=row_index, column=column_index))
        column = self.ordered_columns[column_index]
        return self._format_cell(datum, column)

    def _format_cell(self, obj: object, col: Any | None) -> Any:
        if obj is None:
            return self._format_null()

        if isinstance(obj, str):
            if self.render_markup:
                try:
                    return Text.from_markup(obj)
                except MarkupError:
                    return escape(obj)
            return escape(obj)

        if isinstance(obj, bool):
            return "True" if obj else "False"

        if isinstance(obj, (float, Decimal)):
            return Align(f"{obj:n}", align="right")

        if isinstance(obj, int):
            if col is not None and getattr(col, "is_id", False):
                return Align(str(obj), align="right")
            return Align(f"{obj:n}", align="right")

        if isinstance(obj, (datetime, time)):
            return obj.isoformat(timespec="milliseconds").replace("+00:00", "Z")

        if isinstance(obj, date):
            return obj.isoformat()

        if isinstance(obj, timedelta):
            return str(obj)

        if not is_renderable(obj):
            return str(obj)

        return obj

    def _format_null(self) -> Text:
        null_rep = getattr(self, "null_rep", None)
        if isinstance(null_rep, Text):
            return null_rep
        return Text(str(null_rep) if null_rep is not None else "NULL")


class ResultsTableContainer(Container):
    """A focusable container for the results DataTable.

    This container holds focus when its child DataTable is replaced,
    preventing focus from jumping to another widget during table updates.
    Key events are forwarded to the child DataTable.
    """

    can_focus = True

    def on_key(self, event: Key) -> None:
        """Forward key events to the child DataTable."""
        # Find the DataTable child
        try:
            table = self.query_one(SqlitDataTable)
            # Let the table handle navigation keys
            if event.key in ("up", "down", "left", "right", "pageup", "pagedown", "home", "end"):
                # Simulate the key on the table
                table.post_message(event)
                event.stop()
        except Exception:
            pass

    def on_focus(self, event: Any) -> None:
        """When container gets focus, style it as active."""
        self.add_class("container-focused")

    def on_blur(self, event: Any) -> None:
        """When container loses focus, remove active styling."""
        self.remove_class("container-focused")
