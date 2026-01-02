"""Cursor and navigation actions for query editing."""

from __future__ import annotations

from sqlit.shared.ui.protocols import QueryMixinHost


class QueryEditingCursorMixin:
    """Cursor movement and navigation for the query editor."""

    def action_g_leader_key(self: QueryMixinHost) -> None:
        """Show the g motion leader menu."""
        self._start_leader_pending("g")

    def action_g_first_line(self: QueryMixinHost) -> None:
        """Go to first line (gg)."""
        self._clear_leader_pending()
        self.query_input.cursor_location = (0, 0)

    def action_g_word_end_back(self: QueryMixinHost) -> None:
        """Go to end of previous word (ge)."""
        self._clear_leader_pending()
        from sqlit.domains.query.editing import MOTIONS

        text = self.query_input.text
        row, col = self.query_input.cursor_location
        result = MOTIONS["ge"](text, row, col, None)
        self.query_input.cursor_location = (result.position.row, result.position.col)

    def action_g_WORD_end_back(self: QueryMixinHost) -> None:
        """Go to end of previous WORD (gE)."""
        self._clear_leader_pending()
        from sqlit.domains.query.editing import MOTIONS

        text = self.query_input.text
        row, col = self.query_input.cursor_location
        result = MOTIONS["gE"](text, row, col, None)
        self.query_input.cursor_location = (result.position.row, result.position.col)

    def action_cursor_left(self: QueryMixinHost) -> None:
        """Move cursor left (h in normal mode)."""
        row, col = self.query_input.cursor_location
        self.query_input.cursor_location = (row, max(0, col - 1))

    def action_cursor_right(self: QueryMixinHost) -> None:
        """Move cursor right (l in normal mode)."""
        lines = self.query_input.text.split("\n")
        row, col = self.query_input.cursor_location
        line_len = len(lines[row]) if row < len(lines) else 0
        self.query_input.cursor_location = (row, min(col + 1, line_len))

    def action_cursor_up(self: QueryMixinHost) -> None:
        """Move cursor up (k in normal mode)."""
        lines = self.query_input.text.split("\n")
        row, col = self.query_input.cursor_location
        new_row = max(0, row - 1)
        new_col = min(col, len(lines[new_row]) if new_row < len(lines) else 0)
        self.query_input.cursor_location = (new_row, new_col)

    def action_cursor_down(self: QueryMixinHost) -> None:
        """Move cursor down (j in normal mode)."""
        lines = self.query_input.text.split("\n")
        row, col = self.query_input.cursor_location
        new_row = min(row + 1, len(lines) - 1)
        new_col = min(col, len(lines[new_row]) if new_row < len(lines) else 0)
        self.query_input.cursor_location = (new_row, new_col)

    def action_open_line_below(self: QueryMixinHost) -> None:
        """Open new line below current line and enter insert mode (o in normal mode)."""
        self._push_undo_state()
        lines = self.query_input.text.split("\n")
        row, _ = self.query_input.cursor_location

        # Insert new line after current row
        lines.insert(row + 1, "")
        self.query_input.text = "\n".join(lines)
        self.query_input.cursor_location = (row + 1, 0)

        # Enter insert mode
        self.action_enter_insert_mode()

    def action_open_line_above(self: QueryMixinHost) -> None:
        """Open new line above current line and enter insert mode (O in normal mode)."""
        self._push_undo_state()
        lines = self.query_input.text.split("\n")
        row, _ = self.query_input.cursor_location

        # Insert new line before current row
        lines.insert(row, "")
        self.query_input.text = "\n".join(lines)
        self.query_input.cursor_location = (row, 0)

        # Enter insert mode
        self.action_enter_insert_mode()
