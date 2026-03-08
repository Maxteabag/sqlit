"""Command router for shell commands."""

from __future__ import annotations

from typing import Any, Callable

CommandHandler = Callable[[Any, str, list[str]], bool]

_COMMAND_HANDLERS: list[CommandHandler] = []


def register_command_handler(handler: CommandHandler) -> None:
    """Register a command handler."""
    _COMMAND_HANDLERS.append(handler)


def dispatch_command(app: Any, cmd: str, args: list[str]) -> bool:
    """Dispatch a command to registered handlers."""
    for handler in list(_COMMAND_HANDLERS):
        try:
            if handler(app, cmd, args):
                return True
        except Exception:
            continue
    return False
