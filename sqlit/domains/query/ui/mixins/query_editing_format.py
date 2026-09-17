"""Query formatting action."""

from __future__ import annotations

from sqlit.shared.ui.protocols import QueryMixinHost


class QueryEditingFormatMixin:
    """Format the complete query buffer with sqlparse."""

    def action_format_query(self: QueryMixinHost) -> None:
        from sqlit.domains.query.editing.formatting import (
            format_sql,
            remap_cursor_after_format,
        )

        original = self.query_input.text
        if not original.strip():
            self.notify("Nothing to format", severity="warning")
            return

        formatted = format_sql(original)
        if formatted == original:
            self.notify("Query is already formatted")
            return

        cursor = remap_cursor_after_format(
            original,
            formatted,
            self.query_input.cursor_location,
        )
        self._push_undo_state()
        self.query_input.text = formatted
        self.query_input.cursor_location = cursor
        self.notify("Query formatted")
