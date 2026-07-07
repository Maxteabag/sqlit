"""Query editor focused state."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.state_base import State


class QueryFocusedState(State):
    """Base state when query editor has focus."""

    def _setup_actions(self) -> None:
        # Close autocomplete dropdown if it somehow stays open while leaving
        # INSERT mode (e.g. edge cases or future modes).
        self.allows("autocomplete_close")

    def is_active(self, app: InputContext) -> bool:
        return app.focus == "query"
