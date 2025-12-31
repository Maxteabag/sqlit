"""Explorer tree filter state."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.state_base import BlockingState, DisplayBinding, resolve_display_key


class TreeFilterActiveState(BlockingState):
    """State when tree filter is active."""

    help_category = "Explorer"

    def _setup_actions(self) -> None:
        self.allows("tree_filter_close", help="Close filter")
        self.allows("tree_filter_accept", help="Select item")
        self.allows("tree_filter_next", help="Next match")
        self.allows("tree_filter_prev", help="Previous match")
        self.allows("quit")

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        close_key = resolve_display_key("tree_filter_close") or "esc"
        accept_key = resolve_display_key("tree_filter_accept") or "enter"
        next_key = resolve_display_key("tree_filter_next") or "n"
        prev_key = resolve_display_key("tree_filter_prev") or "N"
        left: list[DisplayBinding] = [
            DisplayBinding(key=close_key, label="Close", action="tree_filter_close"),
            DisplayBinding(key=accept_key, label="Select", action="tree_filter_accept"),
            DisplayBinding(key=f"{next_key}/{prev_key}", label="Next/Prev", action="tree_filter_next"),
        ]
        return left, []

    def is_active(self, app: InputContext) -> bool:
        return app.focus == "explorer" and app.tree_filter_active
