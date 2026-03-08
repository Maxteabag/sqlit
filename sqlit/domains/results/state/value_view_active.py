"""Value view states for tree and syntax modes."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.state_base import DisplayBinding, State


class ValueViewActiveState(State):
    """Base state for inline value view (viewing a cell's full content)."""

    help_category = "Value View"

    def _setup_actions(self) -> None:
        self.allows("close_value_view", key="escape", label="Close", help="Close value view")
        self.allows("close_value_view", key="q", label="Close", help="Close value view")
        self.allows("copy_value_view", key="y", label="Copy", help="Copy value")
        self.allows(
            "toggle_value_view_mode",
            lambda app: app.value_view_is_json,
            key="t",
            label="Toggle",
            help="Toggle tree/syntax view",
        )

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = [
            DisplayBinding(key="esc", label="Close", action="close_value_view"),
            DisplayBinding(key="y", label="Copy", action="copy_value_view"),
        ]
        return left, []

    def is_active(self, app: InputContext) -> bool:
        return app.value_view_active


class ValueViewTreeModeState(State):
    """Value view is in tree mode (JSON tree viewer)."""

    help_category = "Value View"

    def _setup_actions(self) -> None:
        self.allows("collapse_all_json_nodes", key="z", label="Collapse", help="Collapse all nodes")
        self.allows("expand_all_json_nodes", key="Z", label="Expand", help="Expand all nodes")
        self.allows("toggle_value_view_mode", key="t", label="Syntax View", help="Switch to syntax view")

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = [
            DisplayBinding(key="z", label="Collapse", action="collapse_all_json_nodes"),
            DisplayBinding(key="Z", label="Expand", action="expand_all_json_nodes"),
            DisplayBinding(key="t", label="Syntax View", action="toggle_value_view_mode"),
        ]

        # Get parent bindings
        if self.parent:
            parent_left, parent_right = self.parent.get_display_bindings(app)
            seen = {b.action for b in left}
            for binding in parent_left:
                if binding.action not in seen:
                    left.append(binding)
                    seen.add(binding.action)
            return left, parent_right

        return left, []

    def is_active(self, app: InputContext) -> bool:
        return app.value_view_active and app.value_view_is_json and app.value_view_tree_mode


class ValueViewSyntaxModeState(State):
    """Value view is in syntax mode (syntax-highlighted text)."""

    help_category = "Value View"

    def _setup_actions(self) -> None:
        self.allows("toggle_value_view_mode", key="t", label="Tree View", help="Switch to tree view")

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = []

        # Only show Tree toggle for JSON content
        if app.value_view_is_json:
            left.append(DisplayBinding(key="t", label="Tree View", action="toggle_value_view_mode"))

        # Get parent bindings
        if self.parent:
            parent_left, parent_right = self.parent.get_display_bindings(app)
            seen = {b.action for b in left}
            for binding in parent_left:
                if binding.action not in seen:
                    left.append(binding)
                    seen.add(binding.action)
            return left, parent_right

        return left, []

    def is_active(self, app: InputContext) -> bool:
        return app.value_view_active and app.value_view_is_json and not app.value_view_tree_mode
