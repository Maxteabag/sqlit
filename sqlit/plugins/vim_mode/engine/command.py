"""Vim command mode handler.

Handles ex-style commands like :w, :q, :wq, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .engine import VimEngine


class CommandAction(Enum):
    """Actions that can result from command execution."""

    NONE = "none"
    QUIT = "quit"  # Exit without saving
    QUIT_FORCE = "quit_force"  # Exit without saving, discard changes
    WRITE = "write"  # Save to history
    WRITE_QUIT = "write_quit"  # Save and exit


@dataclass
class CommandResult:
    """Result of executing a command."""

    action: CommandAction = CommandAction.NONE
    message: str = ""
    error: bool = False


class VimCommandHandler:
    """Handles vim ex-style commands."""

    def __init__(self) -> None:
        self._command_buffer: str = ""
        self._on_complete: Callable[[CommandResult], None] | None = None

    @property
    def buffer(self) -> str:
        """Get the current command buffer."""
        return self._command_buffer

    def set_callback(self, callback: Callable[[CommandResult], None]) -> None:
        """Set callback for command completion."""
        self._on_complete = callback

    def start(self) -> None:
        """Start command mode."""
        self._command_buffer = ""

    def add_char(self, char: str) -> None:
        """Add a character to the command buffer."""
        if len(char) == 1:
            self._command_buffer += char

    def backspace(self) -> bool:
        """Remove last character. Returns False if buffer is now empty."""
        if self._command_buffer:
            self._command_buffer = self._command_buffer[:-1]
            return True
        return False

    def cancel(self) -> None:
        """Cancel command mode."""
        self._command_buffer = ""
        if self._on_complete:
            self._on_complete(CommandResult(action=CommandAction.NONE))

    def execute(self) -> CommandResult:
        """Execute the current command."""
        cmd = self._command_buffer.strip()
        self._command_buffer = ""

        result = self._parse_and_execute(cmd)

        if self._on_complete:
            self._on_complete(result)

        return result

    def _parse_and_execute(self, cmd: str) -> CommandResult:
        """Parse and execute a command string."""
        if not cmd:
            return CommandResult()

        # Split command into parts
        parts = cmd.split(None, 1)
        base_cmd = parts[0].lower()
        # args = parts[1] if len(parts) > 1 else ""

        # Quit commands
        if base_cmd in ("q", "quit"):
            return CommandResult(action=CommandAction.QUIT)

        if base_cmd in ("q!", "quit!"):
            return CommandResult(action=CommandAction.QUIT_FORCE)

        # Write commands
        if base_cmd in ("w", "write"):
            return CommandResult(
                action=CommandAction.WRITE,
                message="Query saved to history",
            )

        # Write and quit
        if base_cmd in ("wq", "x", "exit"):
            return CommandResult(action=CommandAction.WRITE_QUIT)

        # Help
        if base_cmd in ("h", "help"):
            return CommandResult(
                message="Commands: :q (quit), :w (save), :wq (save & quit), :q! (force quit)",
            )

        # Unknown command
        return CommandResult(
            error=True,
            message=f"Unknown command: {cmd}",
        )
