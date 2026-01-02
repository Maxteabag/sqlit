"""Explorer tree state for index/trigger/sequence nodes."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.state_base import DisplayBinding, State, resolve_display_key


class TreeOnObjectState(State):
    """Tree focused on index, trigger, or sequence node."""

    help_category = "Explorer"

    def _setup_actions(self) -> None:
        self.allows("select_table", label="Show Info", help="Show object definition/info")

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = []
        seen: set[str] = set()

        left.append(
            DisplayBinding(
                key=resolve_display_key("select_table") or "s",
                label="Show Info",
                action="select_table",
            )
        )
        seen.add("select_table")
        left.append(
            DisplayBinding(
                key=resolve_display_key("refresh_tree") or "f",
                label="Refresh",
                action="refresh_tree",
            )
        )
        seen.add("refresh_tree")

        right: list[DisplayBinding] = []
        if self.parent:
            _, parent_right = self.parent.get_display_bindings(app)
            for binding in parent_right:
                if binding.action not in seen:
                    right.append(binding)
                    seen.add(binding.action)

        return left, right

    def is_active(self, app: InputContext) -> bool:
        return app.focus == "explorer" and app.tree_node_kind in ("index", "trigger", "sequence")
