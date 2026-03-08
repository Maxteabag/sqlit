"""Process worker command handlers."""

from __future__ import annotations

import time
from typing import Any

from .router import register_command_handler


def _handle_worker_command(app: Any, cmd: str, args: list[str]) -> bool:
    if cmd in {"worker", "process-worker", "process_worker"} and args:
        subcommand = args[0].lower()
        if subcommand != "info":
            return False
        runtime = getattr(app.services, "runtime", None)
        enabled = bool(getattr(runtime, "process_worker", False)) if runtime else False
        warm_on_idle = bool(getattr(runtime, "process_worker_warm_on_idle", False)) if runtime else False
        auto_shutdown = float(getattr(runtime, "process_worker_auto_shutdown_s", 0) or 0) if runtime else 0.0
        active = getattr(app, "_process_worker_client", None) is not None
        last_used = getattr(app, "_process_worker_last_used", None)
        client_error = getattr(app, "_process_worker_client_error", None)

        if not enabled:
            mode = "disabled"
        else:
            mode = "warm-on-idle" if warm_on_idle else "lazy"

        if last_used is None:
            last_active = "never"
        else:
            age_s = max(0.0, time.monotonic() - float(last_used))
            if age_s < 1:
                last_active = "just now"
            elif age_s < 60:
                last_active = f"{age_s:.1f}s ago"
            elif age_s < 3600:
                last_active = f"{age_s / 60:.1f}m ago"
            elif age_s < 86400:
                last_active = f"{age_s / 3600:.1f}h ago"
            else:
                last_active = f"{age_s / 86400:.1f}d ago"

        auto_shutdown_label = "off" if auto_shutdown <= 0 else f"{auto_shutdown:g}s"

        parts = [
            f"Worker {mode}",
            f"active={'yes' if active else 'no'}",
            f"last={last_active}",
            f"auto={auto_shutdown_label}",
        ]
        if client_error:
            parts.append(f"error={client_error}")
        app.notify(" | ".join(parts))
        return True
    return False


register_command_handler(_handle_worker_command)
