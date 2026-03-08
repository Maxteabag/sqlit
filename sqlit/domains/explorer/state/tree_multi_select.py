"""Explorer tree state for multi-select mode."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.state_base import DisplayBinding, State, resolve_display_key


class TreeMultiSelectState(State):
    """Tree focused while selecting multiple connections (after exiting visual mode)."""

    help_category = "Explorer"

    def _setup_actions(self) -> None:
        self.allows(
            "clear_connection_selection",
            label="Clear",
            help="Clear selection",
        )
        self.allows(
            "move_connection_to_folder",
            label="Move",
            help="Move selected connections",
        )
        self.allows(
            "delete_connection",
            label="Delete",
            help="Delete selected connections",
        )

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = []
        seen: set[str] = set()

        left.append(
            DisplayBinding(
                key=resolve_display_key("clear_connection_selection") or "<esc>",
                label="Clear",
                action="clear_connection_selection",
            )
        )
        seen.add("clear_connection_selection")
        left.append(
            DisplayBinding(
                key=resolve_display_key("move_connection_to_folder") or "m",
                label="Move",
                action="move_connection_to_folder",
            )
        )
        seen.add("move_connection_to_folder")
        left.append(
            DisplayBinding(
                key=resolve_display_key("delete_connection") or "d",
                label="Delete",
                action="delete_connection",
            )
        )
        seen.add("delete_connection")

        if self.parent:
            parent_left, _ = self.parent.get_display_bindings(app)
            for binding in parent_left:
                if binding.action not in seen:
                    left.append(binding)
                    seen.add(binding.action)

        return left, []

    def is_active(self, app: InputContext) -> bool:
        return app.focus == "explorer" and app.tree_multi_select_active
