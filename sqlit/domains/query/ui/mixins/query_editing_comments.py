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
