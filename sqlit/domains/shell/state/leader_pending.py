"""Leader-pending state definitions."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.leader_commands import get_leader_binding_actions, get_leader_commands
from sqlit.core.state_base import ActionResult, DisplayBinding, State


class LeaderPendingState(State):
    """State when waiting for a leader-style combo key."""

    def _setup_actions(self) -> None:
        pass

    def check_action(self, app: InputContext, action_name: str) -> ActionResult:
        menu = app.leader_menu
        leader_binding_actions = get_leader_binding_actions(menu)
        if action_name in leader_binding_actions:
            leader_commands = get_leader_commands(menu)
            cmd = next((c for c in leader_commands if c.binding_action == action_name), None)
            if cmd and cmd.is_allowed(app):
                return ActionResult.ALLOWED
            return ActionResult.FORBIDDEN

        return ActionResult.FORBIDDEN

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        return [], [DisplayBinding(key="...", label="Waiting", action="leader_pending")]

    def is_active(self, app: InputContext) -> bool:
        return app.leader_pending
