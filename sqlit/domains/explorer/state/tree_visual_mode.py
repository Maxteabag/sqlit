"""Explorer tree state for visual selection mode."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.state_base import DisplayBinding, State, resolve_display_key


class TreeVisualModeState(State):
    """Tree focused in visual selection mode (vim-style range selection)."""

    help_category = "Explorer"

    def _setup_actions(self) -> None:
        self.allows(
            "exit_tree_visual_mode",
            label="Exit Visual",
            help="Exit visual selection mode",
        )
        # Block entering visual mode when already in visual mode
        self.forbids("enter_tree_visual_mode")
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
        self.allows(
            "tree_cursor_down",
            label="Extend Down",
            help="Extend selection down",
        )
        self.allows(
            "tree_cursor_up",
            label="Extend Up",
            help="Extend selection up",
        )

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = []
        seen: set[str] = set()

        left.append(
            DisplayBinding(
                key=resolve_display_key("exit_tree_visual_mode") or "<esc>",
                label="Exit Visual",
                action="exit_tree_visual_mode",
            )
        )
        seen.add("exit_tree_visual_mode")
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
        return app.focus == "explorer" and app.tree_visual_mode_active
