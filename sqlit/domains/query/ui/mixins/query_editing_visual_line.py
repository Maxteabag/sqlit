"""Visual line mode actions for query editing."""

from __future__ import annotations

from sqlit.shared.ui.protocols import QueryMixinHost


class QueryEditingVisualLineMixin:
    """Visual line mode (V) for the query editor."""

    _visual_line_anchor_row: int | None = None

    def action_enter_visual_line_mode(self: QueryMixinHost) -> None:
        """Enter visual line mode (V)."""
        from sqlit.core.vim import VimMode
        from textual.widgets.text_area import Selection

        row, _ = self.query_input.cursor_location
        self._visual_line_anchor_row = row
        self.vim_mode = VimMode.VISUAL_LINE

        # Select the full current line
        lines = self.query_input.text.split("\n")
        end_col = len(lines[row]) if row < len(lines) else 0
        self.query_input.selection = Selection((row, 0), (row, end_col))

        self._update_vim_mode_visuals()
        self._update_footer_bindings()

    def action_exit_visual_line_mode(self: QueryMixinHost) -> None:
        """Exit visual line mode back to normal."""
        from sqlit.core.vim import VimMode
        from textual.widgets.text_area import Selection

        self._visual_line_anchor_row = None
        self.vim_mode = VimMode.NORMAL

        # Clear selection
        cursor = self.query_input.cursor_location
        self.query_input.selection = Selection(cursor, cursor)

        self._update_vim_mode_visuals()
        self._update_footer_bindings()

    def _update_visual_line_selection(
        self: QueryMixinHost, cursor_row: int | None = None
    ) -> None:
        """Update selection to span full lines between anchor and cursor.

        Sets the TextArea selection directly, which also positions the cursor
        at the selection end. This avoids setting cursor_location separately,
        which would clear the selection via TextArea internals.
        """
        from textual.widgets.text_area import Selection

        anchor = self._visual_line_anchor_row
        if anchor is None:
            return

        if cursor_row is None:
            cursor_row, _ = self.query_input.cursor_location

        lines = self.query_input.text.split("\n")
        start_row = min(anchor, cursor_row)
        end_row = max(anchor, cursor_row)
        end_col = len(lines[end_row]) if end_row < len(lines) else 0

        # Selection end is where the cursor lands. Place it on the cursor's side
        # so the TextArea cursor follows the direction of movement.
        if cursor_row >= anchor:
            self.query_input.selection = Selection((start_row, 0), (end_row, end_col))
        else:
            self.query_input.selection = Selection((end_row, end_col), (start_row, 0))

    def _get_visual_line_range(self: QueryMixinHost) -> tuple[int, int]:
        """Get the (start_row, end_row) of the visual line selection."""
        anchor = self._visual_line_anchor_row
        if anchor is None:
            row, _ = self.query_input.cursor_location
            return row, row
        cursor_row, _ = self.query_input.cursor_location
        return min(anchor, cursor_row), max(anchor, cursor_row)

    def action_visual_line_yank(self: QueryMixinHost) -> None:
        """Yank (copy) selected lines."""
        from sqlit.domains.query.editing import MotionType, Position, Range, operator_yank

        start_row, end_row = self._get_visual_line_range()
        text = self.query_input.text
        lines = text.split("\n")

        range_obj = Range(
            Position(start_row, 0),
            Position(end_row, len(lines[end_row]) if end_row < len(lines) else 0),
            MotionType.LINEWISE,
        )
        result = operator_yank(text, range_obj)
        if result.yanked:
            self._copy_text(result.yanked)

        # Exit visual line mode before flash
        self._visual_line_anchor_row = None

        from sqlit.core.vim import VimMode

        self.vim_mode = VimMode.NORMAL
        self.query_input.cursor_location = (start_row, 0)

        # _flash_yank_range sets the selection to the yanked range and
        # schedules its own 0.15s timer to clear it back to cursor.
        end_col = len(lines[end_row]) if end_row < len(lines) else 0
        self._flash_yank_range(start_row, 0, end_row, end_col)
        self._update_vim_mode_visuals()
        self._update_footer_bindings()

    def action_visual_line_delete(self: QueryMixinHost) -> None:
        """Delete selected lines."""
        from sqlit.domains.query.editing import MotionType, Position, Range, operator_delete
        from textual.widgets.text_area import Selection

        self._push_undo_state()

        start_row, end_row = self._get_visual_line_range()
        text = self.query_input.text
        lines = text.split("\n")

        range_obj = Range(
            Position(start_row, 0),
            Position(end_row, len(lines[end_row]) if end_row < len(lines) else 0),
            MotionType.LINEWISE,
        )
        result = operator_delete(text, range_obj)

        if result.yanked:
            self._copy_text(result.yanked)

        self.query_input.text = result.text
        self.query_input.cursor_location = (result.row, result.col)

        # Exit visual line mode
        self._visual_line_anchor_row = None

        from sqlit.core.vim import VimMode

        self.vim_mode = VimMode.NORMAL
        cursor = self.query_input.cursor_location
        self.query_input.selection = Selection(cursor, cursor)
        self._update_vim_mode_visuals()
        self._update_footer_bindings()

    def action_visual_line_change(self: QueryMixinHost) -> None:
        """Change (delete + insert mode) selected lines."""
        from sqlit.domains.query.editing import MotionType, Position, Range, operator_delete
        from textual.widgets.text_area import Selection

        self._push_undo_state()

        start_row, end_row = self._get_visual_line_range()
        text = self.query_input.text
        lines = text.split("\n")

        range_obj = Range(
            Position(start_row, 0),
            Position(end_row, len(lines[end_row]) if end_row < len(lines) else 0),
            MotionType.LINEWISE,
        )
        result = operator_delete(text, range_obj)

        if result.yanked:
            self._copy_text(result.yanked)

        self.query_input.text = result.text
        self.query_input.cursor_location = (result.row, result.col)

        # Clear selection and enter insert mode
        self._visual_line_anchor_row = None
        cursor = self.query_input.cursor_location
        self.query_input.selection = Selection(cursor, cursor)
        self._enter_insert_mode()

    def action_visual_line_execute(self: QueryMixinHost) -> None:
        """Execute only the visually selected lines."""
        # _get_query_to_execute already reads from self.query_input.selection,
        # so we just need to trigger execution and then exit visual line mode.
        # Keep the selection active during execution so _get_query_to_execute picks it up.
        self.action_execute_query()

        # Exit visual line mode after triggering execution
        self._visual_line_anchor_row = None

        from sqlit.core.vim import VimMode
        from textual.widgets.text_area import Selection

        self.vim_mode = VimMode.NORMAL
        cursor = self.query_input.cursor_location
        self.query_input.selection = Selection(cursor, cursor)
        self._update_vim_mode_visuals()
        self._update_footer_bindings()
