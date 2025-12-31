"""Query-executing state definitions."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.state_base import DisplayBinding, State, resolve_display_key


class QueryExecutingState(State):
    """State when a query is being executed."""

    help_category = "Query"

    def _setup_actions(self) -> None:
        self.allows("cancel_operation", label="Cancel", help="Cancel query")
        self.allows("quit")

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        key = resolve_display_key("cancel_operation") or "^z"
        left: list[DisplayBinding] = [DisplayBinding(key=key, label="Cancel", action="cancel_operation")]
        return left, []

    def is_active(self, app: InputContext) -> bool:
        if app.modal_open:
            return False
        return app.query_executing
