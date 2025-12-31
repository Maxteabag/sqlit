"""Query editor normal mode state."""

from __future__ import annotations

from sqlit.domains.shell.app.state_base import DisplayBinding, State, resolve_display_key
from sqlit.domains.shell.app.state_context import UIContext
from sqlit.shared.ui.widgets import VimMode


class QueryNormalModeState(State):
    """Query editor in NORMAL mode."""

    help_category = "Query Editor (Normal)"

    def _setup_actions(self) -> None:
        self.allows("enter_insert_mode", label="Insert Mode", help="Enter INSERT mode")
        self.allows("execute_query", label="Execute", help="Execute query")
        self.allows("delete_leader_key", label="Delete", help="Delete (menu)")
        self.allows("new_query", label="New", help="New query (clear all)")
        self.allows("copy_context", label="Copy query", help="Copy current query")
        self.allows("show_history", label="History", help="Query history")
        # Clipboard actions
        self.allows("select_all", help="Select all text")
        self.allows("copy_selection", help="Copy selection")
        self.allows("paste", help="Paste")

    def get_display_bindings(self, app: UIContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        left: list[DisplayBinding] = []
        seen: set[str] = set()

        left.append(
            DisplayBinding(
                key=resolve_display_key("enter_insert_mode") or "i",
                label="Insert Mode",
                action="enter_insert_mode",
            )
        )
        seen.add("enter_insert_mode")
        left.append(
            DisplayBinding(
                key=resolve_display_key("execute_query") or "enter",
                label="Execute",
                action="execute_query",
            )
        )
        seen.add("execute_query")

        left.append(
            DisplayBinding(
                key=resolve_display_key("copy_context") or "y",
                label="Copy query",
                action="copy_context",
            )
        )
        seen.add("copy_context")

        left.append(
            DisplayBinding(
                key=resolve_display_key("show_history") or "h",
                label="History",
                action="show_history",
            )
        )
        seen.add("show_history")

        left.append(
            DisplayBinding(
                key=resolve_display_key("delete_leader_key") or "d",
                label="Delete",
                action="delete_leader_key",
            )
        )
        seen.add("delete_leader_key")
        left.append(
            DisplayBinding(
                key=resolve_display_key("new_query") or "n",
                label="New",
                action="new_query",
            )
        )
        seen.add("new_query")

        right: list[DisplayBinding] = []
        if self.parent:
            _, parent_right = self.parent.get_display_bindings(app)
            for binding in parent_right:
                if binding.action not in seen:
                    right.append(binding)
                    seen.add(binding.action)

        return left, right

    def is_active(self, app: UIContext) -> bool:
        return bool(app.query_input.has_focus) and app.vim_mode == VimMode.NORMAL
