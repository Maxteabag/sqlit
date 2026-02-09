"""Cursor and navigation actions for query editing."""

from __future__ import annotations

from sqlit.shared.ui.protocols import QueryMixinHost


class QueryEditingCursorMixin:
    """Cursor movement and navigation for the query editor."""

    def _move_with_motion(self: QueryMixinHost, motion_key: str, char: str | None = None) -> None:
        """Move cursor using a vim motion, with optional count prefix support."""
        from sqlit.domains.query.editing import MOTIONS

        motion_func = MOTIONS.get(motion_key)
        if not motion_func:
            return

        # Get count prefix (if any)
        count = self._get_and_clear_count() or 1

        text = self.query_input.text
        row, col = self.query_input.cursor_location

        # Apply motion `count` times
        for _ in range(count):
            result = motion_func(text, row, col, char)
            new_row, new_col = result.position.row, result.position.col
            # Stop if motion didn't move (hit boundary)
            if (new_row, new_col) == (row, col):
                break
            row, col = new_row, new_col

        self.query_input.cursor_location = (row, col)

    def action_g_leader_key(self: QueryMixinHost) -> None:
        """Show the g motion leader menu."""
        self._start_leader_pending("g")

    def action_g_first_line(self: QueryMixinHost) -> None:
        """Go to first line (gg), or to line N with count prefix (e.g., 3gg)."""
        self._clear_leader_pending()
        count = self._get_and_clear_count()
        if count is not None:
            lines = self.query_input.text.split("\n")
            num_lines = len(lines)
            target_row = min(count - 1, num_lines - 1)
            target_row = max(0, target_row)
            self.query_input.cursor_location = (target_row, 0)
        else:
            self.query_input.cursor_location = (0, 0)

    def action_g_word_end_back(self: QueryMixinHost) -> None:
        """Go to end of previous word (ge)."""
        self._clear_leader_pending()
        self._move_with_motion("ge")

    def action_g_WORD_end_back(self: QueryMixinHost) -> None:
        """Go to end of previous WORD (gE)."""
        self._clear_leader_pending()
        self._move_with_motion("gE")

    def action_g_execute_single_statement(self: QueryMixinHost) -> None:
        """Execute single statement at cursor via g menu (gs)."""
        self._clear_leader_pending()
        self.action_execute_single_statement()

    def action_g_execute_query(self: QueryMixinHost) -> None:
        """Execute query via g menu (gr)."""
        self._clear_leader_pending()
        self.action_execute_query()

    def action_g_execute_query_atomic(self: QueryMixinHost) -> None:
        """Execute query as transaction via g menu (gt)."""
        self._clear_leader_pending()
        self.action_execute_query_atomic()

    def action_cursor_left(self: QueryMixinHost) -> None:
        """Move cursor left (h in normal mode), with count support."""
        self._move_with_motion("h")

    def action_cursor_right(self: QueryMixinHost) -> None:
        """Move cursor right (l in normal mode), with count support."""
        self._move_with_motion("l")

    def action_cursor_up(self: QueryMixinHost) -> None:
        """Move cursor up (k in normal mode), with count support."""
        self._move_with_motion("k")

    def action_cursor_down(self: QueryMixinHost) -> None:
        """Move cursor down (j in normal mode), with count support."""
        self._move_with_motion("j")

    def action_cursor_word_forward(self: QueryMixinHost) -> None:
        """Move cursor to next word (w)."""
        self._move_with_motion("w")

    def action_cursor_WORD_forward(self: QueryMixinHost) -> None:
        """Move cursor to next WORD (W)."""
        self._move_with_motion("W")

    def action_cursor_word_end(self: QueryMixinHost) -> None:
        """Move cursor to end of word (e)."""
        self._move_with_motion("e")

    def action_cursor_word_back(self: QueryMixinHost) -> None:
        """Move cursor to previous word (b)."""
        self._move_with_motion("b")

    def action_cursor_WORD_back(self: QueryMixinHost) -> None:
        """Move cursor to previous WORD (B)."""
        self._move_with_motion("B")

    def action_cursor_line_start(self: QueryMixinHost) -> None:
        """Move cursor to start of line (0)."""
        self._move_with_motion("0")

    def action_cursor_line_end(self: QueryMixinHost) -> None:
        """Move cursor to end of line ($)."""
        self._move_with_motion("$")

    def action_cursor_last_line(self: QueryMixinHost) -> None:
        """Move cursor to last line (G), or to line N with count prefix (e.g., 25G)."""
        count = self._get_and_clear_count()
        if count is not None:
            # Go to specific line (1-indexed)
            lines = self.query_input.text.split("\n")
            num_lines = len(lines)
            target_row = min(count - 1, num_lines - 1)  # Convert to 0-indexed, clamp
            target_row = max(0, target_row)
            self.query_input.cursor_location = (target_row, 0)
        else:
            # Go to last line
            self._move_with_motion("G")

    def action_cursor_matching_bracket(self: QueryMixinHost) -> None:
        """Move cursor to matching bracket (%)."""
        self._move_with_motion("%")

    def action_cursor_find_char(self: QueryMixinHost) -> None:
        """Find next occurrence of char (f{c})."""
        self._show_motion_char_pending_menu("f")

    def action_cursor_find_char_back(self: QueryMixinHost) -> None:
        """Find previous occurrence of char (F{c})."""
        self._show_motion_char_pending_menu("F")

    def action_cursor_till_char(self: QueryMixinHost) -> None:
        """Move till before next char (t{c})."""
        self._show_motion_char_pending_menu("t")

    def action_cursor_till_char_back(self: QueryMixinHost) -> None:
        """Move till after previous char (T{c})."""
        self._show_motion_char_pending_menu("T")

    def action_prepend_insert_mode(self: QueryMixinHost) -> None:
        """Enter insert mode at start of line (I)."""
        row, _ = self.query_input.cursor_location
        self.query_input.cursor_location = (row, 0)
        self.action_enter_insert_mode()

    def action_append_insert_mode(self: QueryMixinHost) -> None:
        """Enter insert mode after cursor (a)."""
        lines = self.query_input.text.split("\n")
        row, col = self.query_input.cursor_location
        line_len = len(lines[row]) if row < len(lines) else 0
        self.query_input.cursor_location = (row, min(col + 1, line_len))
        self.action_enter_insert_mode()

    def action_append_line_end(self: QueryMixinHost) -> None:
        """Enter insert mode at end of line (A)."""
        lines = self.query_input.text.split("\n")
        row, _ = self.query_input.cursor_location
        line_len = len(lines[row]) if row < len(lines) else 0
        self.query_input.cursor_location = (row, line_len)
        self.action_enter_insert_mode()

    def _show_motion_char_pending_menu(self: QueryMixinHost, motion: str) -> None:
        """Show char pending menu for f/F/t/T motions (cursor movement)."""
        from sqlit.domains.query.ui.screens import CharPendingMenuScreen

        def handle_result(char: str | None) -> None:
            if char:
                self._move_with_motion(motion, char)

        self.push_screen(CharPendingMenuScreen(motion), handle_result)

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
