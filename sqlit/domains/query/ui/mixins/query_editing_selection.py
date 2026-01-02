"""Selection helpers for query editing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlit.shared.ui.protocols import QueryMixinHost

if TYPE_CHECKING:
    from textual.widgets.text_area import Selection

    from sqlit.domains.query.editing.types import Range


class QueryEditingSelectionMixin:
    """Selection-related actions for the query editor."""

    def _ordered_selection(
        self: QueryMixinHost,
        selection: Selection,
    ) -> tuple[tuple[int, int], tuple[int, int]]:
        """Return ordered (start, end) selection coordinates."""
        start = selection.start
        end = selection.end
        if start > end:
            start, end = end, start
        return start, end

    def _selection_range(
        self: QueryMixinHost,
        start: tuple[int, int],
        end: tuple[int, int],
    ) -> Range:
        """Build a charwise range from selection bounds."""
        from sqlit.domains.query.editing.types import MotionType, Position, Range

        return Range(
            Position(start[0], start[1]),
            Position(end[0], end[1]),
            MotionType.CHARWISE,
            inclusive=False,
        )

    def _has_selection(self: QueryMixinHost) -> bool:
        """Check if there's an active text selection."""
        selection = self.query_input.selection
        return selection.start != selection.end

    def _flash_yank_range(
        self: QueryMixinHost,
        start_row: int,
        start_col: int,
        end_row: int,
        end_col: int,
    ) -> None:
        """Flash the yanked range by temporarily selecting it."""
        from textual.widgets.text_area import Selection

        # Save current cursor position
        cursor = self.query_input.cursor_location

        # Set selection to yanked range to highlight it
        self.query_input.selection = Selection(
            (start_row, start_col), (end_row, end_col)
        )

        # Clear selection after a short delay
        def clear_flash() -> None:
            self.query_input.selection = Selection(cursor, cursor)

        self.set_timer(0.15, clear_flash)

    def _yank_selection(self: QueryMixinHost) -> None:
        """Yank the current selection."""
        from textual.widgets.text_area import Selection

        from sqlit.domains.query.editing import get_selection_text

        selection = self.query_input.selection
        start_row, start_col = selection.start
        end_row, end_col = selection.end

        text = get_selection_text(
            self.query_input.text,
            start_row,
            start_col,
            end_row,
            end_col,
        )

        if text:
            self._copy_text(text)
            # Flash: keep selection visible briefly, then clear
            cursor = self.query_input.cursor_location

            def clear_selection() -> None:
                self.query_input.selection = Selection(cursor, cursor)

            self.set_timer(0.15, clear_selection)

    def _change_selection(self: QueryMixinHost) -> None:
        """Change (delete and enter insert mode) the current selection."""
        from textual.widgets.text_area import Selection

        from sqlit.domains.query.editing import get_selection_text, operator_delete

        selection = self.query_input.selection
        start, end = self._ordered_selection(selection)

        # Push undo state before change
        self._push_undo_state()

        text = self.query_input.text

        # Yank text before deleting
        yanked = get_selection_text(text, start[0], start[1], end[0], end[1])
        if yanked:
            self._copy_text(yanked)

        # Delete selection
        range_obj = self._selection_range(start, end)
        result = operator_delete(text, range_obj)
        self.query_input.text = result.text
        self.query_input.cursor_location = (result.row, result.col)

        # Clear selection and enter insert mode
        cursor = self.query_input.cursor_location
        self.query_input.selection = Selection(cursor, cursor)

        # Enter insert mode
        self._enter_insert_mode()

    def _delete_selection(self: QueryMixinHost) -> None:
        """Delete the current selection."""
        from textual.widgets.text_area import Selection

        from sqlit.domains.query.editing import get_selection_text, operator_delete

        selection = self.query_input.selection
        if selection.start == selection.end:
            return

        start, end = self._ordered_selection(selection)

        # Push undo state before delete
        self._push_undo_state()

        text = self.query_input.text

        # Yank text before deleting
        yanked = get_selection_text(text, start[0], start[1], end[0], end[1])
        if yanked:
            self._copy_text(yanked)

        # Delete selection
        range_obj = self._selection_range(start, end)
        result = operator_delete(text, range_obj)
        self.query_input.text = result.text
        self.query_input.cursor_location = (result.row, result.col)

        # Clear selection
        cursor = self.query_input.cursor_location
        self.query_input.selection = Selection(cursor, cursor)

    def _extend_selection(self: QueryMixinHost, new_row: int, new_col: int) -> None:
        """Extend selection from current anchor to new position."""
        from textual.widgets.text_area import Selection

        # Get current selection anchor (start point)
        selection = self.query_input.selection
        anchor = selection.start

        # Update cursor and selection
        self.query_input.cursor_location = (new_row, new_col)
        self.query_input.selection = Selection(anchor, (new_row, new_col))

    def action_select_left(self: QueryMixinHost) -> None:
        """Extend selection one character left (Shift+Left)."""
        row, col = self.query_input.cursor_location
        new_col = max(0, col - 1)
        self._extend_selection(row, new_col)

    def action_select_right(self: QueryMixinHost) -> None:
        """Extend selection one character right (Shift+Right)."""
        lines = self.query_input.text.split("\n")
        row, col = self.query_input.cursor_location
        line_len = len(lines[row]) if row < len(lines) else 0
        new_col = min(col + 1, line_len)
        self._extend_selection(row, new_col)

    def action_select_up(self: QueryMixinHost) -> None:
        """Extend selection one line up (Shift+Up)."""
        lines = self.query_input.text.split("\n")
        row, col = self.query_input.cursor_location
        new_row = max(0, row - 1)
        new_col = min(col, len(lines[new_row]) if new_row < len(lines) else 0)
        self._extend_selection(new_row, new_col)

    def action_select_down(self: QueryMixinHost) -> None:
        """Extend selection one line down (Shift+Down)."""
        lines = self.query_input.text.split("\n")
        row, col = self.query_input.cursor_location
        new_row = min(row + 1, len(lines) - 1)
        new_col = min(col, len(lines[new_row]) if new_row < len(lines) else 0)
        self._extend_selection(new_row, new_col)

    def action_select_word_left(self: QueryMixinHost) -> None:
        """Extend selection one word left (Ctrl+Shift+Left)."""
        from sqlit.domains.query.editing import MOTIONS

        text = self.query_input.text
        row, col = self.query_input.cursor_location
        result = MOTIONS["b"](text, row, col, None)
        self._extend_selection(result.position.row, result.position.col)

    def action_select_word_right(self: QueryMixinHost) -> None:
        """Extend selection one word right (Ctrl+Shift+Right)."""
        from sqlit.domains.query.editing import MOTIONS

        text = self.query_input.text
        row, col = self.query_input.cursor_location
        result = MOTIONS["w"](text, row, col, None)
        self._extend_selection(result.position.row, result.position.col)

    def action_select_line_start(self: QueryMixinHost) -> None:
        """Extend selection to line start (Shift+Home)."""
        row, _ = self.query_input.cursor_location
        self._extend_selection(row, 0)

    def action_select_line_end(self: QueryMixinHost) -> None:
        """Extend selection to line end (Shift+End)."""
        lines = self.query_input.text.split("\n")
        row, _ = self.query_input.cursor_location
        end_col = len(lines[row]) if row < len(lines) else 0
        self._extend_selection(row, end_col)

    def action_select_to_start(self: QueryMixinHost) -> None:
        """Extend selection to document start (Ctrl+Shift+Home)."""
        self._extend_selection(0, 0)

    def action_select_to_end(self: QueryMixinHost) -> None:
        """Extend selection to document end (Ctrl+Shift+End)."""
        lines = self.query_input.text.split("\n")
        last_row = len(lines) - 1
        last_col = len(lines[last_row]) if lines else 0
        self._extend_selection(last_row, last_col)
