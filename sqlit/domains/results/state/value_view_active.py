"""Inline value view state."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.state_base import DisplayBinding, State


class ValueViewActiveState(State):
    """Inline value view is active (viewing a cell's full content)."""

    help_category = "Value View"

    def _setup_actions(self) -> None:
        self.allows("close_value_view", key="escape", label="Close", help="Close value view")
        self.allows("close_value_view", key="q", label="Close", help="Close value view")
        self.allows("copy_value_view", key="y", label="Copy", help="Copy value")

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = [
            DisplayBinding(key="esc", label="Close", action="close_value_view"),
            DisplayBinding(key="y", label="Copy", action="copy_value_view"),
        ]
        return left, []

    def is_active(self, app: InputContext) -> bool:
        return app.value_view_active
