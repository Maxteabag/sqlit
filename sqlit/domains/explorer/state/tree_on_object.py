"""Explorer tree state for index/trigger/sequence nodes."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.state_base import DisplayBinding, State, resolve_display_key


class TreeOnObjectState(State):
    """Tree focused on index, trigger, or sequence node."""

    help_category = "Explorer"

    def _setup_actions(self) -> None:
        self.allows("select_table", label="Open", help="Open the selected object")
        self.allows(
            "rename_saved_query",
            lambda app: app.tree_node_kind == "saved_query_file",
            label="Rename",
            help="Rename saved query",
        )
        self.allows(
            "delete_saved_query",
            lambda app: app.tree_node_kind == "saved_query_file",
            label="Delete",
            help="Delete saved query",
        )

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = []
        seen: set[str] = set()

        label = "Open Query" if app.tree_node_kind == "saved_query_file" else "Show Info"
        left.append(
            DisplayBinding(
                key=resolve_display_key("select_table") or "s",
                label=label,
                action="select_table",
            )
        )
        seen.add("select_table")
        if app.tree_node_kind == "saved_query_file":
            left.extend(
                (
                    DisplayBinding(
                        key=resolve_display_key("rename_saved_query") or "r",
                        label="Rename",
                        action="rename_saved_query",
                    ),
                    DisplayBinding(
                        key=resolve_display_key("delete_saved_query") or "d",
                        label="Delete",
                        action="delete_saved_query",
                    ),
                )
            )
            seen.update({"rename_saved_query", "delete_saved_query"})
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
        return app.focus == "explorer" and app.tree_node_kind in (
            "index",
            "trigger",
            "sequence",
            "saved_query_file",
        )
