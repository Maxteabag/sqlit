"""Leader menu screen for command shortcuts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

from ...widgets import Dialog

if TYPE_CHECKING:
    from ...app import SSMSTUI


class LeaderMenuScreen(ModalScreen):
    """Modal screen showing leader key commands."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=False),
        Binding("space", "dismiss", "Close", show=False),
    ]

    CSS = """
    LeaderMenuScreen {
        align: right bottom;
        background: rgba(0, 0, 0, 0);
        overlay: none;
    }

    #leader-menu {
        max-width: 35;
        margin: 0;
        border: solid $primary;
    }

    #leader-menu-content {
        width: auto;
        height: auto;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        from ...state_machine import get_leader_commands

        leader_commands = get_leader_commands()
        self._cmd_actions = {cmd.action: cmd for cmd in leader_commands}

        for cmd in leader_commands:
            self._bindings.bind(cmd.key, f"cmd_{cmd.action}", cmd.label, show=False)

    def compose(self) -> ComposeResult:
        """Generate menu content from leader commands."""
        from ...state_machine import get_leader_commands

        lines = []
        leader_commands = get_leader_commands()
        app = cast("SSMSTUI", self.app)

        categories: dict[str, list] = {}
        for cmd in leader_commands:
            if cmd.category not in categories:
                categories[cmd.category] = []
            categories[cmd.category].append(cmd)

        for category, commands in categories.items():
            lines.append(f"[bold $text-muted]{category}[/]")
            for cmd in commands:
                if cmd.is_allowed(app):
                    lines.append(f"  [bold $warning]{cmd.key}[/] {cmd.label}")
            lines.append("")

        # Remove trailing empty line
        if lines and lines[-1] == "":
            lines.pop()

        content = "\n".join(lines)
        with Dialog(id="leader-menu", shortcuts=[("Close", "esc")]):
            yield Static(content, id="leader-menu-content")

    def action_dismiss(self) -> None:  # type: ignore[override]
        self.dismiss(None)

    def _run_and_dismiss(self, action_name: str) -> None:
        """Run an app action and dismiss the menu."""
        self.dismiss(action_name)

    def __getattr__(self, name: str) -> Any:
        """Handle cmd_* actions dynamically from leader commands."""
        if name.startswith("action_cmd_"):
            action = name[len("action_cmd_") :]
            if action in self._cmd_actions:
                cmd = self._cmd_actions[action]

                def handler() -> None:
                    if cmd.is_allowed(cast("SSMSTUI", self.app)):
                        self._run_and_dismiss(cmd.action)

                return handler
        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")
