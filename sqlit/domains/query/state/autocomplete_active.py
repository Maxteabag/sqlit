"""Query editor autocomplete state."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.state_base import DisplayBinding, State, resolve_display_key
from sqlit.core.vim import VimMode


class AutocompleteActiveState(State):
    """Query editor with autocomplete dropdown visible."""

    help_category = "Query Editor (Insert)"

    def _setup_actions(self) -> None:
        self.allows("autocomplete_next", help="Next suggestion", help_key="^j")
        self.allows("autocomplete_prev", help="Previous suggestion", help_key="^k")
        self.allows("autocomplete_accept", help="Accept autocomplete", help_key="tab")
        self.allows("autocomplete_close", help="Close autocomplete", help_key="esc")
        self.allows("execute_query_insert")
        self.allows("quit")
        self.forbids(
            "exit_insert_mode",  # Escape closes autocomplete, not exits insert mode
            "focus_explorer",
            "focus_results",
            "leader_key",
            "new_connection",
            "show_help",
        )

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        accept_key = resolve_display_key("autocomplete_accept") or "tab"
        next_key = resolve_display_key("autocomplete_next") or "^j"
        prev_key = resolve_display_key("autocomplete_prev") or "^k"
        close_key = resolve_display_key("autocomplete_close") or "esc"
        left: list[DisplayBinding] = [
            DisplayBinding(key=accept_key, label="Accept", action="autocomplete_accept"),
            DisplayBinding(key=f"{next_key}/{prev_key}", label="Next/Prev", action="autocomplete_next"),
            DisplayBinding(key=close_key, label="Close", action="autocomplete_close"),
        ]
        return left, []

    def is_active(self, app: InputContext) -> bool:
        return app.focus == "query" and app.vim_mode == VimMode.INSERT and app.autocomplete_visible
