"""Comment toggle actions for query editing."""

from __future__ import annotations

from sqlit.shared.ui.protocols import QueryMixinHost


class QueryEditingCommentsMixin:
    """Comment-related actions for the query editor."""

    def action_g_comment(self: QueryMixinHost) -> None:
        """Open the comment submenu (gc)."""
        self._clear_leader_pending()
        self._start_leader_pending("gc")

    def action_gc_line(self: QueryMixinHost) -> None:
        """Toggle comment on current line (gcc)."""
        self._clear_leader_pending()
        self._push_undo_state()
        from sqlit.domains.query.editing.comments import toggle_comment_lines

        text = self.query_input.text
        row, _ = self.query_input.cursor_location
        new_text, new_col = toggle_comment_lines(text, row, row)
        self.query_input.text = new_text
        self.query_input.cursor_location = (row, new_col)

    def action_gc_down(self: QueryMixinHost) -> None:
        """Toggle comment on current line and line below (gcj)."""
        self._clear_leader_pending()
        self._push_undo_state()
        from sqlit.domains.query.editing.comments import toggle_comment_lines

        text = self.query_input.text
        row, _ = self.query_input.cursor_location
        lines = text.split("\n")
        end_row = min(row + 1, len(lines) - 1)
        new_text, new_col = toggle_comment_lines(text, row, end_row)
        self.query_input.text = new_text
        self.query_input.cursor_location = (row, new_col)

    def action_gc_up(self: QueryMixinHost) -> None:
        """Toggle comment on current line and line above (gck)."""
        self._clear_leader_pending()
        self._push_undo_state()
        from sqlit.domains.query.editing.comments import toggle_comment_lines

        text = self.query_input.text
        row, _ = self.query_input.cursor_location
        start_row = max(row - 1, 0)
        new_text, new_col = toggle_comment_lines(text, start_row, row)
        self.query_input.text = new_text
        self.query_input.cursor_location = (start_row, new_col)

    def action_gc_to_end(self: QueryMixinHost) -> None:
        """Toggle comment from current line to end (gcG)."""
        self._clear_leader_pending()
        self._push_undo_state()
        from sqlit.domains.query.editing.comments import toggle_comment_lines

        text = self.query_input.text
        row, _ = self.query_input.cursor_location
        lines = text.split("\n")
        end_row = len(lines) - 1
        new_text, new_col = toggle_comment_lines(text, row, end_row)
        self.query_input.text = new_text
        self.query_input.cursor_location = (row, new_col)

    def action_gc_selection(self: QueryMixinHost) -> None:
        """Toggle comment on currently selected text (gcs)."""
        self._clear_leader_pending()

        if not self._has_selection():
            return

        self._push_undo_state()
        from sqlit.domains.query.editing.comments import toggle_comment_lines

        selection = self.query_input.selection
        start, end = self._ordered_selection(selection)

        start_row = start[0]
        end_row = end[0]

        # If selection ends at the start of a line, don't include that line
        if end[1] == 0 and end_row > start_row:
            end_row -= 1

        text = self.query_input.text
        new_text, new_col = toggle_comment_lines(text, start_row, end_row)
        self.query_input.text = new_text
        self.query_input.cursor_location = (start_row, new_col)

    def action_gc_statement(self: QueryMixinHost) -> None:
        """Toggle comment on statement at cursor (gcS)."""
        self._clear_leader_pending()
        from sqlit.domains.query.app.multi_statement import find_statement_at_cursor
        from sqlit.domains.query.editing.comments import toggle_comment_lines

        text = self.query_input.text
        if not text or not text.strip():
            return

        row, col = self.query_input.cursor_location
        result = find_statement_at_cursor(text, row, col)

        if result is None:
            return

        _, start_offset, end_offset = result

        # Convert character offsets to line numbers
        start_row = text[:start_offset].count("\n")
        end_row = text[:end_offset].count("\n")

        self._push_undo_state()
        new_text, new_col = toggle_comment_lines(text, start_row, end_row)
        self.query_input.text = new_text
        self.query_input.cursor_location = (start_row, new_col)
