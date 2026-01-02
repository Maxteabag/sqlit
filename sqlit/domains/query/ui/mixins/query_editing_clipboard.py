"""Clipboard actions for query editing."""

from __future__ import annotations

from sqlit.shared.ui.protocols import QueryMixinHost


class QueryEditingClipboardMixin:
    """Clipboard-related actions for the query editor."""

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
            start, end = self._ordered_selection(selection)
            # Delete selection by replacing with paste content
            from sqlit.domains.query.editing import operator_delete

            range_obj = self._selection_range(start, end)
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
