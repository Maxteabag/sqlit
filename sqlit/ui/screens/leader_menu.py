"""Leader menu screen for command shortcuts."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

from ...state_machine import get_leader_commands


def _make_menu_bindings():
    """Generate bindings for the leader menu from leader commands."""
    bindings = [
        Binding("escape", "dismiss", "Close", show=False),
        Binding("space", "dismiss", "Close", show=False),
    ]
    for cmd in get_leader_commands():
        # Menu uses cmd_* action names which dismiss and return the target action
        bindings.append(Binding(cmd.key, f"cmd_{cmd.action}", cmd.label, show=False))
    return bindings


class LeaderMenuScreen(ModalScreen):
    """Modal screen showing leader key commands."""

    BINDINGS = _make_menu_bindings()

    CSS = """
    LeaderMenuScreen {
        align: right bottom;
        background: rgba(0, 0, 0, 0);
        overlay: none;
    }

    #leader-menu {
        width: auto;
        height: auto;
        max-width: 50;
        background: $surface;
        border: solid $primary;
        padding: 1;
        margin: 1 2;
    }
    """

    def __init__(self):
        super().__init__()
        # Build lookup for cmd_* actions (rebuilt each time for testability)
        self._cmd_actions = {cmd.action: cmd for cmd in get_leader_commands()}

    def compose(self) -> ComposeResult:
        """Generate menu content from leader commands."""
        lines = []
        leader_commands = get_leader_commands()

        categories: dict[str, list] = {}
        for cmd in leader_commands:
            if cmd.category not in categories:
                categories[cmd.category] = []
            categories[cmd.category].append(cmd)

        for category, commands in categories.items():
            lines.append(f"[bold $text-muted]{category}[/]")
            for cmd in commands:
                if cmd.is_allowed(self.app):
                    lines.append(f"  [bold $warning]{cmd.key}[/] {cmd.label}")
            lines.append("")

        lines.append("[$primary]Close: <esc>[/]")

        content = "\n".join(lines)
        yield Static(content, id="leader-menu")

    def action_dismiss(self) -> None:
        self.dismiss(None)

    def _run_and_dismiss(self, action_name: str) -> None:
        """Run an app action and dismiss the menu."""
        self.dismiss(action_name)

    def __getattr__(self, name: str):
        """Handle cmd_* actions dynamically from leader commands."""
        if name.startswith("action_cmd_"):
            action = name[len("action_cmd_"):]
            if action in self._cmd_actions:
                cmd = self._cmd_actions[action]

                def handler():
                    if cmd.is_allowed(self.app):
                        self._run_and_dismiss(cmd.action)

                return handler
        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")
