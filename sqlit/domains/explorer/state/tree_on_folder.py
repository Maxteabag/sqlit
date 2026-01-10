"""Explorer tree state for folder/schema nodes."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.state_base import DisplayBinding, State, resolve_display_key


class TreeOnFolderState(State):
    """Tree focused on a folder or schema node."""

    def _setup_actions(self) -> None:
        def is_connection_folder(app: InputContext) -> bool:
            return app.tree_node_kind == "connection_folder"

        self.allows(
            "rename_connection_folder",
            is_connection_folder,
            label="Rename",
            help="Rename connection folder",
        )
        self.allows(
            "delete_connection_folder",
            is_connection_folder,
            label="Delete",
            help="Delete connection folder",
        )

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = []
        seen: set[str] = set()

        left.append(DisplayBinding(key="enter", label="Expand", action="toggle_node"))
        seen.add("toggle_node")
        left.append(
            DisplayBinding(
                key=resolve_display_key("refresh_tree") or "f",
                label="Refresh",
                action="refresh_tree",
            )
        )
        seen.add("refresh_tree")

        if app.tree_node_kind == "connection_folder":
            left.append(
                DisplayBinding(
                    key=resolve_display_key("rename_connection_folder") or "M",
                    label="Rename",
                    action="rename_connection_folder",
                )
            )
            seen.add("rename_connection_folder")
            left.append(
                DisplayBinding(
                    key=resolve_display_key("delete_connection_folder") or "d",
                    label="Delete",
                    action="delete_connection_folder",
                )
            )
            seen.add("delete_connection_folder")

        right: list[DisplayBinding] = []
        if self.parent:
            _, parent_right = self.parent.get_display_bindings(app)
            for binding in parent_right:
                if binding.action not in seen:
                    right.append(binding)
                    seen.add(binding.action)

        return left, right

    def is_active(self, app: InputContext) -> bool:
        return app.focus == "explorer" and app.tree_node_kind in ("folder", "schema", "connection_folder")
