"""Editing actions for the query editor."""

from __future__ import annotations

from typing import Any

from sqlit.domains.query.editing import deletion as edit_delete
from sqlit.shared.ui.protocols import QueryMixinHost


class QueryEditingMixin:
    """Mixin providing query editing actions."""
    def action_copy_query(self: QueryMixinHost) -> None:
        """Copy the current query to clipboard."""
        from sqlit.shared.ui.widgets import flash_widget

        query = self.query_input.text.strip()
        if not query:
            self.notify("Query is empty", severity="warning")
            return
        self._copy_text(query)
        flash_widget(self.query_input)

    def action_copy_context(self: QueryMixinHost) -> None:
        """Copy based on current focus (query or results)."""
        if self.query_input.has_focus:
            self.action_copy_query()
            return
        if self.results_table.has_focus:
            self.action_copy_cell()
            return
        self.notify("Nothing to copy", severity="warning")

    def action_delete_line(self: QueryMixinHost) -> None:
        """Delete the current line in the query editor."""
        self._clear_leader_pending()
        result = edit_delete.delete_line(
            self.query_input.text,
            *self.query_input.cursor_location,
        )
        self._apply_edit_result(result)

    def action_delete_word(self: QueryMixinHost) -> None:
        """Delete forward word starting at cursor."""
        self._clear_leader_pending()
        result = edit_delete.delete_word(
            self.query_input.text,
            *self.query_input.cursor_location,
        )
        self._apply_edit_result(result)

    def action_delete_word_back(self: QueryMixinHost) -> None:
        """Delete word backwards from cursor."""
        self._clear_leader_pending()
        result = edit_delete.delete_word_back(
            self.query_input.text,
            *self.query_input.cursor_location,
        )
        self._apply_edit_result(result)

    def action_delete_word_end(self: QueryMixinHost) -> None:
        """Delete through the end of the current word."""
        self._clear_leader_pending()
        result = edit_delete.delete_word_end(
            self.query_input.text,
            *self.query_input.cursor_location,
        )
        self._apply_edit_result(result)

    def action_delete_line_start(self: QueryMixinHost) -> None:
        """Delete from line start to cursor."""
        self._clear_leader_pending()
        result = edit_delete.delete_line_start(
            self.query_input.text,
            *self.query_input.cursor_location,
        )
        self._apply_edit_result(result)

    def action_delete_line_end(self: QueryMixinHost) -> None:
        """Delete from cursor to line end."""
        self._clear_leader_pending()
        result = edit_delete.delete_line_end(
            self.query_input.text,
            *self.query_input.cursor_location,
        )
        self._apply_edit_result(result)

    def action_delete_char(self: QueryMixinHost) -> None:
        """Delete the character under the cursor."""
        self._clear_leader_pending()
        result = edit_delete.delete_char(
            self.query_input.text,
            *self.query_input.cursor_location,
        )
        self._apply_edit_result(result)

    def action_delete_char_back(self: QueryMixinHost) -> None:
        """Delete the character before the cursor."""
        self._clear_leader_pending()
        result = edit_delete.delete_char_back(
            self.query_input.text,
            *self.query_input.cursor_location,
        )
        self._apply_edit_result(result)

    def action_delete_to_end(self: QueryMixinHost) -> None:
        """Delete from cursor to end of buffer."""
        self._clear_leader_pending()
        result = edit_delete.delete_to_end(
            self.query_input.text,
            *self.query_input.cursor_location,
        )
        self._apply_edit_result(result)

    def action_delete_all(self: QueryMixinHost) -> None:
        """Delete all query text."""
        self._clear_leader_pending()
        result = edit_delete.delete_all(
            self.query_input.text,
            *self.query_input.cursor_location,
        )
        self._apply_edit_result(result)

    # ========================================================================
    # New vim motion delete actions
    # ========================================================================

    def action_delete_WORD(self: QueryMixinHost) -> None:
        """Delete WORD (whitespace-delimited) forward."""
        self._clear_leader_pending()
        self._delete_with_motion("W")

    def action_delete_WORD_back(self: QueryMixinHost) -> None:
        """Delete WORD backward."""
        self._clear_leader_pending()
        self._delete_with_motion("B")

    def action_delete_WORD_end(self: QueryMixinHost) -> None:
        """Delete to WORD end."""
        self._clear_leader_pending()
        self._delete_with_motion("E")

    def action_delete_left(self: QueryMixinHost) -> None:
        """Delete character to the left (like backspace)."""
        self._clear_leader_pending()
        self._delete_with_motion("h")

    def action_delete_right(self: QueryMixinHost) -> None:
        """Delete character to the right."""
        self._clear_leader_pending()
        self._delete_with_motion("l")

    def action_delete_up(self: QueryMixinHost) -> None:
        """Delete current and previous line."""
        self._clear_leader_pending()
        self._delete_with_motion("k")

    def action_delete_down(self: QueryMixinHost) -> None:
        """Delete current and next line."""
        self._clear_leader_pending()
        self._delete_with_motion("j")

    def action_delete_line_end_motion(self: QueryMixinHost) -> None:
        """Delete to end of line ($ motion)."""
        self._clear_leader_pending()
        self._delete_with_motion("$")

    def action_delete_matching_bracket(self: QueryMixinHost) -> None:
        """Delete to matching bracket."""
        self._clear_leader_pending()
        self._delete_with_motion("%")

    def action_delete_find_char(self: QueryMixinHost) -> None:
        """Start delete to char (f motion) - shows menu for char input."""
        self._clear_leader_pending()
        self._show_char_pending_menu("f")

    def action_delete_find_char_back(self: QueryMixinHost) -> None:
        """Start delete back to char (F motion) - shows menu for char input."""
        self._clear_leader_pending()
        self._show_char_pending_menu("F")

    def action_delete_till_char(self: QueryMixinHost) -> None:
        """Start delete till char (t motion) - shows menu for char input."""
        self._clear_leader_pending()
        self._show_char_pending_menu("t")

    def action_delete_till_char_back(self: QueryMixinHost) -> None:
        """Start delete back till char (T motion) - shows menu for char input."""
        self._clear_leader_pending()
        self._show_char_pending_menu("T")

    def action_delete_inner(self: QueryMixinHost) -> None:
        """Start delete inside text object - shows menu for object selection."""
        self._clear_leader_pending()
        self._show_text_object_menu("inner")

    def action_delete_around(self: QueryMixinHost) -> None:
        """Start delete around text object - shows menu for object selection."""
        self._clear_leader_pending()
        self._show_text_object_menu("around")

    def _show_char_pending_menu(self: QueryMixinHost, motion: str) -> None:
        """Show the char pending menu and handle the result."""
        from sqlit.domains.query.ui.screens import CharPendingMenuScreen

        def handle_result(char: str | None) -> None:
            if char:
                self._delete_with_motion(motion, char)

        self.push_screen(CharPendingMenuScreen(motion), handle_result)

    def _show_text_object_menu(self: QueryMixinHost, mode: str) -> None:
        """Show the text object menu and handle the result."""
        from sqlit.domains.query.ui.screens import TextObjectMenuScreen

        def handle_result(obj_char: str | None) -> None:
            if obj_char:
                around = mode == "around"
                self._delete_with_text_object(obj_char, around)

        self.push_screen(TextObjectMenuScreen(mode, operator="delete"), handle_result)

    def _delete_with_motion(self: QueryMixinHost, motion_key: str, char: str | None = None) -> None:
        """Execute delete with a motion."""
        from sqlit.domains.query.editing import MOTIONS, operator_delete

        motion_func = MOTIONS.get(motion_key)
        if not motion_func:
            return

        text = self.query_input.text
        row, col = self.query_input.cursor_location

        result = motion_func(text, row, col, char)
        if not result.range:
            return

        # Push undo state before delete
        self._push_undo_state()

        op_result = operator_delete(text, result.range)
        self.query_input.text = op_result.text
        self.query_input.cursor_location = (op_result.row, op_result.col)

        # Copy deleted text to system clipboard
        if op_result.yanked:
            self._copy_text(op_result.yanked)

    def _delete_with_text_object(self: QueryMixinHost, obj_char: str, around: bool) -> None:
        """Execute delete with a text object."""
        from sqlit.domains.query.editing import get_text_object, operator_delete

        text = self.query_input.text
        row, col = self.query_input.cursor_location

        range_obj = get_text_object(obj_char, text, row, col, around)
        if not range_obj:
            return

        # Push undo state before delete
        self._push_undo_state()

        op_result = operator_delete(text, range_obj)
        self.query_input.text = op_result.text
        self.query_input.cursor_location = (op_result.row, op_result.col)

        # Copy deleted text to system clipboard
        if op_result.yanked:
            self._copy_text(op_result.yanked)

    # ========================================================================
    # Yank (y) operator actions
    # ========================================================================

    def _has_selection(self: QueryMixinHost) -> bool:
        """Check if there's an active text selection."""
        selection = self.query_input.selection
        return selection.start != selection.end

    def action_yank_leader_key(self: QueryMixinHost) -> None:
        """Handle yank key - selection-aware.

        If there's a selection, yank it immediately.
        Otherwise, show the yank leader menu.
        """
        if self._has_selection():
            self._yank_selection()
        else:
            self._start_leader_pending("yank")

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

    def action_yank_line(self: QueryMixinHost) -> None:
        """Yank the current line (yy)."""
        self._clear_leader_pending()
        self._yank_with_motion("_")  # _ is the line motion

    def action_yank_word(self: QueryMixinHost) -> None:
        """Yank word forward (yw)."""
        self._clear_leader_pending()
        self._yank_with_motion("w")

    def action_yank_WORD(self: QueryMixinHost) -> None:
        """Yank WORD forward (yW)."""
        self._clear_leader_pending()
        self._yank_with_motion("W")

    def action_yank_word_back(self: QueryMixinHost) -> None:
        """Yank word backward (yb)."""
        self._clear_leader_pending()
        self._yank_with_motion("b")

    def action_yank_WORD_back(self: QueryMixinHost) -> None:
        """Yank WORD backward (yB)."""
        self._clear_leader_pending()
        self._yank_with_motion("B")

    def action_yank_word_end(self: QueryMixinHost) -> None:
        """Yank to word end (ye)."""
        self._clear_leader_pending()
        self._yank_with_motion("e")

    def action_yank_WORD_end(self: QueryMixinHost) -> None:
        """Yank to WORD end (yE)."""
        self._clear_leader_pending()
        self._yank_with_motion("E")

    def action_yank_line_start(self: QueryMixinHost) -> None:
        """Yank to line start (y0)."""
        self._clear_leader_pending()
        self._yank_with_motion("0")

    def action_yank_line_end_motion(self: QueryMixinHost) -> None:
        """Yank to line end (y$)."""
        self._clear_leader_pending()
        self._yank_with_motion("$")

    def action_yank_left(self: QueryMixinHost) -> None:
        """Yank character to the left (yh)."""
        self._clear_leader_pending()
        self._yank_with_motion("h")

    def action_yank_right(self: QueryMixinHost) -> None:
        """Yank character to the right (yl)."""
        self._clear_leader_pending()
        self._yank_with_motion("l")

    def action_yank_up(self: QueryMixinHost) -> None:
        """Yank current and previous line (yk)."""
        self._clear_leader_pending()
        self._yank_with_motion("k")

    def action_yank_down(self: QueryMixinHost) -> None:
        """Yank current and next line (yj)."""
        self._clear_leader_pending()
        self._yank_with_motion("j")

    def action_yank_to_end(self: QueryMixinHost) -> None:
        """Yank to end of buffer (yG)."""
        self._clear_leader_pending()
        self._yank_with_motion("G")

    def action_yank_matching_bracket(self: QueryMixinHost) -> None:
        """Yank to matching bracket (y%)."""
        self._clear_leader_pending()
        self._yank_with_motion("%")

    def action_yank_find_char(self: QueryMixinHost) -> None:
        """Start yank to char (yf) - shows menu for char input."""
        self._clear_leader_pending()
        self._show_yank_char_pending_menu("f")

    def action_yank_find_char_back(self: QueryMixinHost) -> None:
        """Start yank back to char (yF) - shows menu for char input."""
        self._clear_leader_pending()
        self._show_yank_char_pending_menu("F")

    def action_yank_till_char(self: QueryMixinHost) -> None:
        """Start yank till char (yt) - shows menu for char input."""
        self._clear_leader_pending()
        self._show_yank_char_pending_menu("t")

    def action_yank_till_char_back(self: QueryMixinHost) -> None:
        """Start yank back till char (yT) - shows menu for char input."""
        self._clear_leader_pending()
        self._show_yank_char_pending_menu("T")

    def action_yank_inner(self: QueryMixinHost) -> None:
        """Start yank inside text object - shows menu for object selection."""
        self._clear_leader_pending()
        self._show_yank_text_object_menu("inner")

    def action_yank_around(self: QueryMixinHost) -> None:
        """Start yank around text object - shows menu for object selection."""
        self._clear_leader_pending()
        self._show_yank_text_object_menu("around")

    def _show_yank_char_pending_menu(self: QueryMixinHost, motion: str) -> None:
        """Show the char pending menu for yank and handle the result."""
        from sqlit.domains.query.ui.screens import CharPendingMenuScreen

        def handle_result(char: str | None) -> None:
            if char:
                self._yank_with_motion(motion, char)

        self.push_screen(CharPendingMenuScreen(motion), handle_result)

    def _show_yank_text_object_menu(self: QueryMixinHost, mode: str) -> None:
        """Show the text object menu for yank and handle the result."""
        from sqlit.domains.query.ui.screens import TextObjectMenuScreen

        def handle_result(obj_char: str | None) -> None:
            if obj_char:
                around = mode == "around"
                self._yank_with_text_object(obj_char, around)

        self.push_screen(TextObjectMenuScreen(mode, operator="yank"), handle_result)

    def _yank_with_motion(self: QueryMixinHost, motion_key: str, char: str | None = None) -> None:
        """Execute yank with a motion."""
        from sqlit.domains.query.editing import MOTIONS, operator_yank

        motion_func = MOTIONS.get(motion_key)
        if not motion_func:
            return

        text = self.query_input.text
        row, col = self.query_input.cursor_location

        result = motion_func(text, row, col, char)
        if not result.range:
            return

        op_result = operator_yank(text, result.range)

        # Copy yanked text to system clipboard
        if op_result.yanked:
            self._copy_text(op_result.yanked)
            # Flash the yanked range
            ordered = result.range.ordered()
            self._flash_yank_range(
                ordered.start.row, ordered.start.col,
                ordered.end.row, ordered.end.col,
            )

    def _yank_with_text_object(self: QueryMixinHost, obj_char: str, around: bool) -> None:
        """Execute yank with a text object."""
        from sqlit.domains.query.editing import get_text_object, operator_yank

        text = self.query_input.text
        row, col = self.query_input.cursor_location

        range_obj = get_text_object(obj_char, text, row, col, around)
        if not range_obj:
            return

        op_result = operator_yank(text, range_obj)

        # Copy yanked text to system clipboard
        if op_result.yanked:
            self._copy_text(op_result.yanked)
            # Flash the yanked range
            ordered = range_obj.ordered()
            self._flash_yank_range(
                ordered.start.row, ordered.start.col,
                ordered.end.row, ordered.end.col,
            )

    # ========================================================================
    # Change (c) operator actions
    # ========================================================================

    def action_change_leader_key(self: QueryMixinHost) -> None:
        """Handle change key - selection-aware.

        If there's a selection, change it immediately (delete + insert mode).
        Otherwise, show the change leader menu.
        """
        if self._has_selection():
            self._change_selection()
        else:
            self._start_leader_pending("change")

    def _change_selection(self: QueryMixinHost) -> None:
        """Change (delete and enter insert mode) the current selection."""
        from sqlit.domains.query.editing import get_selection_text, operator_delete
        from sqlit.domains.query.editing.types import MotionType, Position, Range

        selection = self.query_input.selection
        start = selection.start
        end = selection.end

        # Order the selection
        if start > end:
            start, end = end, start

        # Push undo state before change
        self._push_undo_state()

        text = self.query_input.text

        # Yank text before deleting
        yanked = get_selection_text(text, start[0], start[1], end[0], end[1])
        if yanked:
            self._copy_text(yanked)

        # Delete selection
        range_obj = Range(
            Position(start[0], start[1]),
            Position(end[0], end[1]),
            MotionType.CHARWISE,
            inclusive=False,
        )
        result = operator_delete(text, range_obj)
        self.query_input.text = result.text
        self.query_input.cursor_location = (result.row, result.col)

        # Clear selection and enter insert mode
        from textual.widgets.text_area import Selection
        cursor = self.query_input.cursor_location
        self.query_input.selection = Selection(cursor, cursor)

        # Enter insert mode
        self._enter_insert_mode()

    def _enter_insert_mode(self: QueryMixinHost) -> None:
        """Enter INSERT mode."""
        from sqlit.core.vim import VimMode

        self.vim_mode = VimMode.INSERT
        self.query_input.read_only = False
        self.query_input.focus()
        self._update_footer_bindings()
        self._update_status_bar()

    def action_change_line(self: QueryMixinHost) -> None:
        """Change the current line (cc)."""
        self._clear_leader_pending()
        self._change_with_motion("_")  # _ is the line motion

    def action_change_word(self: QueryMixinHost) -> None:
        """Change word forward (cw)."""
        self._clear_leader_pending()
        self._change_with_motion("w")

    def action_change_WORD(self: QueryMixinHost) -> None:
        """Change WORD forward (cW)."""
        self._clear_leader_pending()
        self._change_with_motion("W")

    def action_change_word_back(self: QueryMixinHost) -> None:
        """Change word backward (cb)."""
        self._clear_leader_pending()
        self._change_with_motion("b")

    def action_change_WORD_back(self: QueryMixinHost) -> None:
        """Change WORD backward (cB)."""
        self._clear_leader_pending()
        self._change_with_motion("B")

    def action_change_word_end(self: QueryMixinHost) -> None:
        """Change to word end (ce)."""
        self._clear_leader_pending()
        self._change_with_motion("e")

    def action_change_WORD_end(self: QueryMixinHost) -> None:
        """Change to WORD end (cE)."""
        self._clear_leader_pending()
        self._change_with_motion("E")

    def action_change_line_start(self: QueryMixinHost) -> None:
        """Change to line start (c0)."""
        self._clear_leader_pending()
        self._change_with_motion("0")

    def action_change_line_end_motion(self: QueryMixinHost) -> None:
        """Change to line end (c$)."""
        self._clear_leader_pending()
        self._change_with_motion("$")

    def action_change_left(self: QueryMixinHost) -> None:
        """Change character to the left (ch)."""
        self._clear_leader_pending()
        self._change_with_motion("h")

    def action_change_right(self: QueryMixinHost) -> None:
        """Change character to the right (cl)."""
        self._clear_leader_pending()
        self._change_with_motion("l")

    def action_change_up(self: QueryMixinHost) -> None:
        """Change current and previous line (ck)."""
        self._clear_leader_pending()
        self._change_with_motion("k")

    def action_change_down(self: QueryMixinHost) -> None:
        """Change current and next line (cj)."""
        self._clear_leader_pending()
        self._change_with_motion("j")

    def action_change_to_end(self: QueryMixinHost) -> None:
        """Change to end of buffer (cG)."""
        self._clear_leader_pending()
        self._change_with_motion("G")

    def action_change_matching_bracket(self: QueryMixinHost) -> None:
        """Change to matching bracket (c%)."""
        self._clear_leader_pending()
        self._change_with_motion("%")

    def action_change_find_char(self: QueryMixinHost) -> None:
        """Start change to char (cf) - shows menu for char input."""
        self._clear_leader_pending()
        self._show_change_char_pending_menu("f")

    def action_change_find_char_back(self: QueryMixinHost) -> None:
        """Start change back to char (cF) - shows menu for char input."""
        self._clear_leader_pending()
        self._show_change_char_pending_menu("F")

    def action_change_till_char(self: QueryMixinHost) -> None:
        """Start change till char (ct) - shows menu for char input."""
        self._clear_leader_pending()
        self._show_change_char_pending_menu("t")

    def action_change_till_char_back(self: QueryMixinHost) -> None:
        """Start change back till char (cT) - shows menu for char input."""
        self._clear_leader_pending()
        self._show_change_char_pending_menu("T")

    def action_change_inner(self: QueryMixinHost) -> None:
        """Start change inside text object - shows menu for object selection."""
        self._clear_leader_pending()
        self._show_change_text_object_menu("inner")

    def action_change_around(self: QueryMixinHost) -> None:
        """Start change around text object - shows menu for object selection."""
        self._clear_leader_pending()
        self._show_change_text_object_menu("around")

    def _show_change_char_pending_menu(self: QueryMixinHost, motion: str) -> None:
        """Show the char pending menu for change and handle the result."""
        from sqlit.domains.query.ui.screens import CharPendingMenuScreen

        def handle_result(char: str | None) -> None:
            if char:
                self._change_with_motion(motion, char)

        self.push_screen(CharPendingMenuScreen(motion), handle_result)

    def _show_change_text_object_menu(self: QueryMixinHost, mode: str) -> None:
        """Show the text object menu for change and handle the result."""
        from sqlit.domains.query.ui.screens import TextObjectMenuScreen

        def handle_result(obj_char: str | None) -> None:
            if obj_char:
                around = mode == "around"
                self._change_with_text_object(obj_char, around)

        self.push_screen(TextObjectMenuScreen(mode, operator="change"), handle_result)

    def _change_with_motion(self: QueryMixinHost, motion_key: str, char: str | None = None) -> None:
        """Execute change with a motion (delete + enter insert mode)."""
        from sqlit.domains.query.editing import MOTIONS, operator_change

        motion_func = MOTIONS.get(motion_key)
        if not motion_func:
            return

        text = self.query_input.text
        row, col = self.query_input.cursor_location

        result = motion_func(text, row, col, char)
        if not result.range:
            return

        # Push undo state before change
        self._push_undo_state()

        op_result = operator_change(text, result.range)
        self.query_input.text = op_result.text
        self.query_input.cursor_location = (op_result.row, op_result.col)

        # Copy changed text to system clipboard
        if op_result.yanked:
            self._copy_text(op_result.yanked)

        # Enter insert mode if operator requests it
        if op_result.enter_insert:
            self._enter_insert_mode()

    def _change_with_text_object(self: QueryMixinHost, obj_char: str, around: bool) -> None:
        """Execute change with a text object (delete + enter insert mode)."""
        from sqlit.domains.query.editing import get_text_object, operator_change

        text = self.query_input.text
        row, col = self.query_input.cursor_location

        range_obj = get_text_object(obj_char, text, row, col, around)
        if not range_obj:
            return

        # Push undo state before change
        self._push_undo_state()

        op_result = operator_change(text, range_obj)
        self.query_input.text = op_result.text
        self.query_input.cursor_location = (op_result.row, op_result.col)

        # Copy changed text to system clipboard
        if op_result.yanked:
            self._copy_text(op_result.yanked)

        # Enter insert mode if operator requests it
        if op_result.enter_insert:
            self._enter_insert_mode()

    def _delete_selection(self: QueryMixinHost) -> None:
        """Delete the current selection."""
        from sqlit.domains.query.editing import get_selection_text, operator_delete
        from sqlit.domains.query.editing.types import MotionType, Position, Range

        selection = self.query_input.selection
        if selection.start == selection.end:
            return

        start = selection.start
        end = selection.end

        # Order the selection
        if start > end:
            start, end = end, start

        # Push undo state before delete
        self._push_undo_state()

        text = self.query_input.text

        # Yank text before deleting
        yanked = get_selection_text(text, start[0], start[1], end[0], end[1])
        if yanked:
            self._copy_text(yanked)

        # Delete selection
        range_obj = Range(
            Position(start[0], start[1]),
            Position(end[0], end[1]),
            MotionType.CHARWISE,
            inclusive=False,
        )
        result = operator_delete(text, range_obj)
        self.query_input.text = result.text
        self.query_input.cursor_location = (result.row, result.col)

        # Clear selection
        from textual.widgets.text_area import Selection

        cursor = self.query_input.cursor_location
        self.query_input.selection = Selection(cursor, cursor)

    # ========================================================================
    # g motion actions (gg, ge, gE)
    # ========================================================================

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

    def action_g_comment(self: QueryMixinHost) -> None:
        """Open the comment submenu (gc)."""
        self._clear_leader_pending()
        self._start_leader_pending("gc")

    # ========================================================================
    # Comment toggle actions (gcc, gcj, gck, gcG)
    # ========================================================================

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

    # ========================================================================
    # Vim cursor movement (h/j/k/l in normal mode)
    # ========================================================================

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

    def _clear_leader_pending(self: QueryMixinHost) -> None:
        """Clear any leader pending state if supported by the host."""
        cancel = getattr(self, "_cancel_leader_pending", None)
        if callable(cancel):
            cancel()

    def _apply_edit_result(self: QueryMixinHost, result: edit_delete.EditResult) -> None:
        # Push undo state before applying changes
        self._push_undo_state()
        self.query_input.text = result.text
        self.query_input.cursor_location = (max(0, result.row), max(0, result.col))

    # ========================================================================
    # Clipboard actions (CTRL+A/C/V)
    # ========================================================================

    def action_select_all(self: QueryMixinHost) -> None:
        """Select all text in query editor (CTRL+A)."""
        from textual.widgets.text_area import Selection

        from sqlit.domains.query.editing import select_all_range

        text = self.query_input.text
        if not text:
            return

        start_row, start_col, end_row, end_col = select_all_range(text)
        # TextArea selection requires a Selection object
        self.query_input.selection = Selection(
            (start_row, start_col), (end_row, end_col)
        )

    def action_copy_selection(self: QueryMixinHost) -> None:
        """Copy selected text to clipboard (CTRL+C)."""
        from sqlit.domains.query.editing import get_selection_text

        selection = self.query_input.selection
        # Check if there's an actual selection (start != end)
        if selection.start == selection.end:
            # No selection, copy current line or do nothing
            return

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

    def action_paste(self: QueryMixinHost) -> None:
        """Paste text from clipboard (CTRL+V)."""
        from textual.widgets.text_area import Selection

        from sqlit.domains.query.editing import paste_text

        clipboard = self._get_clipboard_text()
        if not clipboard:
            return

        # Push undo state before paste
        self._push_undo_state()

        text = self.query_input.text
        row, col = self.query_input.cursor_location

        # If there's a selection, delete it first
        selection = self.query_input.selection
        if selection.start != selection.end:
            start = selection.start
            end = selection.end
            # Order the selection
            if start > end:
                start, end = end, start
            # Delete selection by replacing with paste content
            from sqlit.domains.query.editing import operator_delete
            from sqlit.domains.query.editing.types import MotionType, Position, Range

            range_obj = Range(
                Position(start[0], start[1]),
                Position(end[0], end[1]),
                MotionType.CHARWISE,
                inclusive=False,
            )
            result = operator_delete(text, range_obj)
            text = result.text
            row, col = result.row, result.col

        paste_result = paste_text(text, row, col, clipboard)
        self.query_input.text = paste_result.text
        self.query_input.cursor_location = (paste_result.row, paste_result.col)
        # Clear selection by setting cursor position (start == end)
        cursor = self.query_input.cursor_location
        self.query_input.selection = Selection(cursor, cursor)

    def _get_clipboard_text(self: QueryMixinHost) -> str:
        """Get text from system clipboard."""
        try:
            import pyperclip  # pyright: ignore[reportMissingModuleSource]
            return pyperclip.paste() or ""
        except Exception:
            return ""

    # ========================================================================
    # Selection actions (Shift+Arrow, Ctrl+Shift+Arrow)
    # ========================================================================

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

    # ========================================================================
    # Undo/Redo actions
    # ========================================================================

    def _get_undo_history(self: QueryMixinHost) -> Any:
        """Get or create the undo history instance."""
        from sqlit.domains.query.editing import UndoHistory

        if self._undo_history is None:
            self._undo_history = UndoHistory()
        return self._undo_history

    def _push_undo_state(self: QueryMixinHost) -> None:
        """Push current state to undo history."""
        history = self._get_undo_history()
        text = self.query_input.text
        row, col = self.query_input.cursor_location
        history.push(text, row, col)

    def action_undo(self: QueryMixinHost) -> None:
        """Undo the last edit."""
        history = self._get_undo_history()
        if not history.can_undo():
            return

        state = history.undo()
        if state:
            self.query_input.text = state.text
            self.query_input.cursor_location = (state.cursor_row, state.cursor_col)

    def action_redo(self: QueryMixinHost) -> None:
        """Redo the last undone edit."""
        history = self._get_undo_history()
        if not history.can_redo():
            return

        state = history.redo()
        if state:
            self.query_input.text = state.text
            self.query_input.cursor_location = (state.cursor_row, state.cursor_col)
