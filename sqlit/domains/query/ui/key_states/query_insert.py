"""Query editor insert mode state."""

from __future__ import annotations

from sqlit.domains.shell.app.state_base import DisplayBinding, State, resolve_display_key, resolve_help_key
from sqlit.domains.shell.app.state_context import UIContext
from sqlit.shared.ui.widgets import VimMode


class QueryInsertModeState(State):
    """Query editor in INSERT mode."""

    help_category = "Query Editor (Insert)"

    def _setup_actions(self) -> None:
        self.allows("exit_insert_mode", label="Normal Mode", help="Exit to NORMAL mode")
        self.allows("execute_query_insert", label="Execute", help="Execute query (stay INSERT)")
        self.allows("autocomplete_accept", help="Accept autocomplete")
        self.allows("quit")
        # Clipboard actions
        self.allows("select_all", help="Select all text")
        self.allows("copy_selection", help="Copy selection")
        self.allows("paste", help="Paste")
        self.forbids(
            "focus_explorer",
            "focus_results",
            "leader_key",
            "new_connection",
            "show_help",
        )

    def get_display_bindings(self, app: UIContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        execute_key = resolve_help_key("execute_query_insert") or resolve_display_key("execute_query_insert") or "f5"
        left: list[DisplayBinding] = [
            DisplayBinding(
                key=resolve_display_key("exit_insert_mode") or "esc",
                label="Normal Mode",
                action="exit_insert_mode",
            ),
            DisplayBinding(
                key=execute_key,
                label="Execute",
                action="execute_query_insert",
            ),
            DisplayBinding(
                key=resolve_display_key("autocomplete_accept") or "tab",
                label="Autocomplete",
                action="autocomplete_accept",
            ),
        ]
        return left, []

    def is_active(self, app: UIContext) -> bool:
        if not app.query_input.has_focus or app.vim_mode != VimMode.INSERT:
            return False
        return not getattr(app, "_autocomplete_visible", False)
