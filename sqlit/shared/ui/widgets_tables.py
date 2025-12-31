"""Table widgets for sqlit."""

from __future__ import annotations

from typing import Any

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
