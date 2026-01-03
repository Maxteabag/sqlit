"""Command handlers for shell app."""

from __future__ import annotations

from .router import dispatch_command, register_command_handler
from . import watchdog as _watchdog

__all__ = ["dispatch_command", "register_command_handler"]
