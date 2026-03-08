"""Char pending menu screen for f/F/t/T motions."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Static

from sqlit.shared.ui.widgets import Dialog


class CharPendingMenuScreen(ModalScreen[str | None]):
    """Modal screen showing hint for char pending (f/F/t/T) motions."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    CSS = """
    CharPendingMenuScreen {
        align: right bottom;
        background: rgba(0, 0, 0, 0);
        overlay: none;
    }

    #char-pending-menu {
        max-width: 30;
        margin: 0;
        border: solid $primary;
    }

    #char-pending-menu-content {
        width: auto;
        height: auto;
    }
    """

    def __init__(self, motion: str) -> None:
        super().__init__()
        self._motion = motion

    def compose(self) -> ComposeResult:
        motion_desc = {
            "f": ("Find char", "Delete to next occurrence of char"),
            "F": ("Find char back", "Delete to previous occurrence of char"),
            "t": ("Till char", "Delete till before next char"),
            "T": ("Till char back", "Delete till after previous char"),
        }.get(self._motion, ("Char", "Delete to char"))

        title, desc = motion_desc

        content = f"""[bold $text-muted]{title}[/]
  {desc}

[bold $warning]Type any character...[/]
  [dim]or press ESC to cancel[/]"""

        with Dialog(id="char-pending-menu", shortcuts=[("Cancel", "esc")]):
            yield Static(content, id="char-pending-menu-content")

    def on_key(self, event: Any) -> None:
        """Capture the target character."""
        if event.key == "escape":
            self.dismiss(None)
            event.stop()
            return

        # Accept any single character
        char = event.character if hasattr(event, "character") else None
        if char and len(char) == 1:
            self.dismiss(char)
            event.stop()

    def action_cancel(self) -> None:
        self.dismiss(None)
