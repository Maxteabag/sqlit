"""Modal-active state definitions."""

from __future__ import annotations

from sqlit.core.input_context import InputContext
from sqlit.core.state_base import ActionResult, DisplayBinding, State


class ModalActiveState(State):
    """State when a modal screen is active."""

    def _setup_actions(self) -> None:
        pass

    def check_action(self, app: InputContext, action_name: str) -> ActionResult:
        if action_name in ("quit",):
            return ActionResult.ALLOWED
        return ActionResult.FORBIDDEN

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        return [], []

    def is_active(self, app: InputContext) -> bool:
        return app.modal_open
