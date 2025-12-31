"""Leader command registry (UI-agnostic)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlit.core.input_context import InputContext
from sqlit.core.keymap import get_keymap

LEADER_GUARDS: dict[str, Callable[[InputContext], bool]] = {
    "has_connection": lambda ctx: ctx.has_connection,
    "query_executing": lambda ctx: ctx.query_executing,
}


@dataclass
class LeaderCommand:
    """Definition of a leader command accessible via space+key."""

    key: str  # The key to press (e.g., "q", "e")
    action: str  # The underlying action to execute (e.g., "quit", "toggle_explorer")
    label: str  # Display label (e.g., "Quit", "Toggle Explorer")
    category: str  # For grouping in the menu ("View", "Connection", "Actions")
    guard: Callable[[InputContext], bool] | None = None  # Optional guard function
    menu: str = "leader"

    @property
    def binding_action(self) -> str:
        """The action name used in bindings (leader-prefixed)."""
        return f"{self.menu}_{self.action}"

    def is_allowed(self, ctx: InputContext) -> bool:
        """Check if this command is currently allowed."""
        if self.guard is None:
            return True
        return self.guard(ctx)


def _build_leader_commands(menu: str = "leader") -> list[LeaderCommand]:
    """Build leader commands from the keymap provider."""
    keymap = get_keymap()
    commands: list[LeaderCommand] = []

    for cmd_def in keymap.get_leader_commands():
        if cmd_def.menu != menu:
            continue
        guard = LEADER_GUARDS.get(cmd_def.guard) if cmd_def.guard else None
        commands.append(
            LeaderCommand(
                key=cmd_def.key,
                action=cmd_def.action,
                label=cmd_def.label,
                category=cmd_def.category,
                guard=guard,
                menu=cmd_def.menu,
            )
        )
    return commands


def get_leader_commands(menu: str = "leader") -> list[LeaderCommand]:
    """Get leader commands (rebuilt from keymap each time for testability)."""
    return _build_leader_commands(menu)


def get_leader_binding_actions(menu: str = "leader") -> set[str]:
    """Get set of leader binding action names."""
    return {cmd.binding_action for cmd in get_leader_commands(menu)}
