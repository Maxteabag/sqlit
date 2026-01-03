"""Main screen state definitions."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.state_base import State


class MainScreenState(State):
    """Base state for main screen (no modal active)."""

    help_category = "Navigation"

    def _setup_actions(self) -> None:
        self.allows("focus_explorer", help="Focus Explorer")
        self.allows("focus_query", help="Focus Query")
        self.allows("focus_results", help="Focus Results")
        self.allows("show_connection_picker")
        self.allows("disconnect", guard=lambda app: app.has_connection)
        self.allows("toggle_fullscreen", help="Toggle fullscreen")
        self.allows("show_help")
        self.allows("change_theme")
        self.allows("toggle_process_worker", help="Toggle process worker")
        self.allows("leader_key", label="Commands", right=True)

    def is_active(self, app: InputContext) -> bool:
        if app.modal_open:
            return False
        return not app.query_executing
