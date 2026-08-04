"""Explorer tree state for table/view nodes."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.state_base import DisplayBinding, State, resolve_display_key


class TreeOnTableState(State):
    """Tree focused on table or view node."""

    help_category = "Explorer"

    def _setup_actions(self) -> None:
        self.allows("select_table", label="Select TOP 100", help="Select TOP 100 (table/view)")
        self.allows(
            "drop_table",
            guard=lambda app: app.tree_node_kind == "table" and app.current_provider_supports_drop_table,
            label="Drop Table",
            help="Drop selected Table",
        )

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = []
        seen: set[str] = set()

        left.append(DisplayBinding(key="enter", label="Columns", action="toggle_node"))
        seen.add("toggle_node")
        left.append(
            DisplayBinding(
                key=resolve_display_key("select_table") or "s",
                label="Select TOP 100",
                action="select_table",
            )
        )
        seen.add("select_table")
        if app.tree_node_kind == "table" and app.current_provider_supports_drop_table:
            left.append(
                DisplayBinding(
                    key=resolve_display_key("drop_table") or "d",
                    label="Drop Table",
                    action="drop_table",
                )
            )
            seen.add("drop_table")
        left.append(
            DisplayBinding(
                key=resolve_display_key("refresh_tree") or "f",
                label="Refresh",
                action="refresh_tree",
            )
        )
        seen.add("refresh_tree")

        if self.parent:
            parent_left, _ = self.parent.get_display_bindings(app)
            for binding in parent_left:
                if binding.action not in seen:
                    left.append(binding)
                    seen.add(binding.action)

        return left, []

    def is_active(self, app: InputContext) -> bool:
        return app.focus == "explorer" and app.tree_node_kind in ("table", "view")
