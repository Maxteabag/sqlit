"""Leader menu screen for command shortcuts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

from sqlit.core.keymap import format_key
from sqlit.core.leader_commands import get_leader_commands
from sqlit.shared.ui.widgets import Dialog

if TYPE_CHECKING:
    from sqlit.domains.shell.app.main import SSMSTUI


class LeaderMenuScreen(ModalScreen):
    """Modal screen showing leader key commands."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=False),
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

    def __init__(self, menu: str = "leader") -> None:
        super().__init__()
        self._menu = menu
        leader_commands = get_leader_commands(menu)
        self._cmd_actions = {cmd.binding_action: cmd for cmd in leader_commands}
        self._cmd_by_key = {cmd.key: cmd for cmd in leader_commands}

        for cmd in leader_commands:
            self._bindings.bind(cmd.key, f"cmd_{cmd.binding_action}", cmd.label, show=False)

    def compose(self) -> ComposeResult:
        """Generate menu content from leader commands."""
        lines = []
        leader_commands = get_leader_commands(self._menu)
        app = cast("SSMSTUI", self.app)
        ctx = app._get_input_context()

        categories: dict[str, list] = {}
        for cmd in leader_commands:
            if cmd.category not in categories:
                categories[cmd.category] = []
            categories[cmd.category].append(cmd)

        for category, commands in categories.items():
            lines.append(f"[bold $text-muted]{category}[/]")
            for cmd in commands:
                if cmd.is_allowed(ctx):
                    lines.append(f"  [bold $warning]{format_key(cmd.key)}[/] {cmd.label}")
            lines.append("")

        # Remove trailing empty line
        if lines and lines[-1] == "":
            lines.pop()

        content = "\n".join(lines)
        with Dialog(id="leader-menu", shortcuts=[("Close", "esc")]):
            yield Static(content, id="leader-menu-content")

    def action_dismiss(self) -> None:  # type: ignore[override]
        self.dismiss(None)

    def on_key(self, event: Any) -> None:
        """Handle key events - explicit ESC handling."""
        if event.key == "escape":
            self.dismiss(None)
            event.stop()
            return
        if event.key == "space":
            cmd = self._cmd_by_key.get("space")
            if cmd:
                app = cast("SSMSTUI", self.app)
                if cmd.is_allowed(app._get_input_context()):
                    self._run_and_dismiss(cmd.binding_action)
                    event.stop()
                    return
            self.dismiss(None)
            event.stop()

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
                    app = cast("SSMSTUI", self.app)
                    if cmd.is_allowed(app._get_input_context()):
                        self._run_and_dismiss(cmd.binding_action)

                return handler
        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")
