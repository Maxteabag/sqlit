"""Root state definitions."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.state_base import State


class RootState(State):
    """Root state - minimal actions available everywhere."""

    help_category = "General"

    def _setup_actions(self) -> None:
        self.allows("quit", help="Quit")
        self.allows("show_help", help="Show this help")
        self.allows("leader_key", help="Commands menu")

    def is_active(self, app: InputContext) -> bool:
        return True
