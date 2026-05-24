"""Visual (charwise) mode actions for query editing."""

from __future__ import annotations

from sqlit.shared.ui.protocols import QueryMixinHost


class QueryEditingVisualMixin:
    """Visual mode (v) for the query editor — charwise selection."""

    _visual_anchor: tuple[int, int] | None = None
    _visual_cursor: tuple[int, int] | None = None

    def action_enter_visual_mode(self: QueryMixinHost) -> None:
        """Enter charwise visual mode (v)."""
        from sqlit.core.vim import VimMode

        cursor = self.query_input.cursor_location
        self._visual_anchor = cursor
        self._visual_cursor = cursor
        self.vim_mode = VimMode.VISUAL
        self._update_query_visual_selection(cursor=cursor)
        self._update_vim_mode_visuals()
        self._update_footer_bindings()

    def action_exit_visual_mode(self: QueryMixinHost) -> None:
        """Exit visual mode back to normal."""
        from sqlit.core.vim import VimMode
        from textual.widgets.text_area import Selection

        self._visual_anchor = None
        self._visual_cursor = None
        self.vim_mode = VimMode.NORMAL
        cursor = self.query_input.cursor_location
        self.query_input.selection = Selection(cursor, cursor)
        self._update_vim_mode_visuals()
        self._update_footer_bindings()

    def action_switch_to_visual_line_mode(self: QueryMixinHost) -> None:
        """Switch from charwise visual to visual line mode (V)."""
        from sqlit.core.vim import VimMode

        cursor_row, _ = self.query_input.cursor_location
        anchor = self._visual_anchor
        anchor_row = anchor[0] if anchor else cursor_row

        self._visual_anchor = None
        self._visual_cursor = None
        self._visual_line_anchor_row = anchor_row
        self.vim_mode = VimMode.VISUAL_LINE
        self._update_visual_line_selection(cursor_row=cursor_row)
        self._update_vim_mode_visuals()
        self._update_footer_bindings()

    def action_switch_to_visual_mode(self: QueryMixinHost) -> None:
        """Switch from visual line to charwise visual mode (v)."""
        from sqlit.core.vim import VimMode

        cursor = self.query_input.cursor_location
        anchor_row = self._visual_line_anchor_row
        anchor = (anchor_row, 0) if anchor_row is not None else cursor

        self._visual_line_anchor_row = None
        self._visual_anchor = anchor
        self.vim_mode = VimMode.VISUAL
        self._update_query_visual_selection(cursor=cursor)
        self._update_vim_mode_visuals()
        self._update_footer_bindings()

    def _update_query_visual_selection(
        self: QueryMixinHost, cursor: tuple[int, int] | None = None
    ) -> None:
        """Update selection from anchor to cursor position.

        Vim visual mode is inclusive — both the anchor and cursor characters
        are part of the selection. Textual's Selection is half-open (end is
        exclusive), so we extend the far end by one character.

        The logical cursor position is stored in _visual_cursor so that
        motion functions read the correct position (not the extended one).
        """
        from textual.widgets.text_area import Selection

        anchor = self._visual_anchor
        if anchor is None:
            return

        if cursor is None:
            cursor = self._visual_cursor or self.query_input.cursor_location

        self._visual_cursor = cursor
        lines = self.query_input.text.split("\n")

        if cursor >= anchor:
            # Forward: extend cursor end by 1 to include cursor char
            row, col = cursor
            end_col = min(col + 1, len(lines[row]) if row < len(lines) else 0)
            self.query_input.selection = Selection(anchor, (row, end_col))
        else:
            # Backward: extend anchor end by 1 to include anchor char
            a_row, a_col = anchor
            end_col = min(a_col + 1, len(lines[a_row]) if a_row < len(lines) else 0)
            self.query_input.selection = Selection((a_row, end_col), cursor)

    def action_visual_yank(self: QueryMixinHost) -> None:
        """Yank the charwise selection."""
        from sqlit.domains.query.editing import get_selection_text

        start, end = self._ordered_selection(self.query_input.selection)
        text = get_selection_text(
            self.query_input.text, start[0], start[1], end[0], end[1]
        )
        if text:
            self._copy_text(text)

        from sqlit.core.vim import VimMode

        self._visual_anchor = None
        self._visual_cursor = None
        self.vim_mode = VimMode.NORMAL
        self.query_input.cursor_location = (start[0], start[1])

        # _flash_yank_range sets the selection to the yanked range and
        # schedules its own 0.15s timer to clear it back to cursor.
        self._flash_yank_range(start[0], start[1], end[0], end[1])
        self._update_vim_mode_visuals()
        self._update_footer_bindings()

    def action_visual_delete(self: QueryMixinHost) -> None:
        """Delete the charwise selection."""
        self._push_undo_state()
        self._delete_selection()

        self._visual_anchor = None
        self._visual_cursor = None

        from sqlit.core.vim import VimMode

        self.vim_mode = VimMode.NORMAL
        self._update_vim_mode_visuals()
        self._update_footer_bindings()

    def action_visual_change(self: QueryMixinHost) -> None:
        """Change (delete + insert) the charwise selection."""
        self._visual_anchor = None
        self._visual_cursor = None
        self._push_undo_state()
        # _change_selection calls _enter_insert_mode which handles
        # vim_mode, visuals, and footer updates.
        self._change_selection()

    def action_visual_execute(self: QueryMixinHost) -> None:
        """Execute the visually selected text."""
        self.action_execute_query()

        self._visual_anchor = None
        self._visual_cursor = None

        from sqlit.core.vim import VimMode
        from textual.widgets.text_area import Selection

        self.vim_mode = VimMode.NORMAL
        cursor = self.query_input.cursor_location
        self.query_input.selection = Selection(cursor, cursor)
        self._update_vim_mode_visuals()
        self._update_footer_bindings()
