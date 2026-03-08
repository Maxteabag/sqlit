"""Undo/redo helpers for query editing."""

from __future__ import annotations

from typing import Any

from sqlit.shared.ui.protocols import QueryMixinHost


class QueryEditingUndoMixin:
    """Undo history management for the query editor."""

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
