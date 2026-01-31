"""Command handlers for shell app."""

from __future__ import annotations

from .router import dispatch_command, register_command_handler
from . import alert as _alert
from . import credentials as _credentials
from . import debug as _debug
from . import watchdog as _watchdog
from . import worker as _worker

__all__ = ["dispatch_command", "register_command_handler"]
