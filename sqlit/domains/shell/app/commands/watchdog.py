"""UI stall watchdog command handlers."""

from __future__ import annotations

import time
from typing import Any

from .router import register_command_handler


def _handle_watchdog_command(app: Any, cmd: str, args: list[str]) -> bool:
    if cmd in {"watchdog", "wd"}:
        value = args[0].lower() if args else ""
        if value == "info":
            from sqlit.shared.ui.screens.message import MessageScreen

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

            lines = [
                "Process worker status:",
                f"Enabled: {'yes' if enabled else 'no'}",
                f"Mode: {mode}",
                f"Active: {'yes' if active else 'no'}",
                f"Last active: {last_active}",
                f"Auto-shutdown: {auto_shutdown_label}",
            ]
            if client_error:
                lines.append(f"Last error: {client_error}")
            app.push_screen(MessageScreen("Process Worker Info", "\n".join(lines)))
            return True
        if value == "list":
            events = getattr(app, "_ui_stall_watchdog_events", [])
            if not events:
                app.notify("No UI stall warnings recorded")
                return True
            from sqlit.shared.ui.screens.message import MessageScreen

            lines = ["Recent UI stall warnings:"]
            path = getattr(app, "_ui_stall_watchdog_log_path", None)
            if path:
                lines.append(f"Log file: {path}")
                lines.append("")
            for ts, ms, suffix in events[-10:]:
                prefix = f"[{ts}]" if ts else "[?]"
                lines.append(f"{prefix} {ms:.1f} ms{suffix}")
            app.push_screen(MessageScreen("UI Stall Watchdog", "\n".join(lines)))
            return True
        if value == "clear":
            try:
                app._ui_stall_watchdog_events = []
            except Exception:
                pass
            path = getattr(app, "_ui_stall_watchdog_log_path", None)
            if path:
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        path.parent.chmod(0o700)
                    except OSError:
                        pass
                    with path.open("w", encoding="utf-8"):
                        pass
                except Exception:
                    app.notify("Failed to clear UI stall log", severity="warning")
                    return True
            app.notify("UI stall watchdog log cleared")
            return True
        if not value:
            current = float(getattr(app.services.runtime, "ui_stall_watchdog_ms", 0) or 0)
            if current > 0:
                path = getattr(app, "_ui_stall_watchdog_log_path", None)
                suffix = f" (log: {path})" if path else ""
                app.notify(f"UI stall watchdog {current:g}ms{suffix}")
            else:
                app.notify("UI stall watchdog disabled")
            return True
        return _handle_watchdog_set(app, "ui_stall_watchdog_ms", value)

    if cmd == "set" and args:
        target = args[0].lower().replace("-", "_")
        value = args[1].lower() if len(args) > 1 else ""
        return _handle_watchdog_set(app, target, value)

    return False


def _handle_watchdog_set(app: Any, target: str, value: str) -> bool:
    if target not in {"ui_stall_watchdog", "ui_stall_watchdog_ms"}:
        return False

    if not value:
        app.notify("Provide ms or 'off' for ui_stall_watchdog_ms", severity="warning")
        return True

    disable_values = {"0", "false", "off", "no", "disable", "disabled"}
    if value in disable_values:
        _set_ui_stall_watchdog_ms(app, 0.0)
        return True

    try:
        ms = float(value)
    except ValueError:
        app.notify(f"Invalid ui_stall_watchdog_ms value: {value}", severity="warning")
        return True

    if ms < 0:
        app.notify("ui_stall_watchdog_ms must be >= 0", severity="warning")
        return True

    _set_ui_stall_watchdog_ms(app, ms)
    return True


def _set_ui_stall_watchdog_ms(app: Any, ms: float) -> None:
    app.services.runtime.ui_stall_watchdog_ms = float(ms)
    try:
        app.services.settings_store.set("ui_stall_watchdog_ms", float(ms))
    except Exception:
        pass

    if ms <= 0:
        timer = getattr(app, "_ui_stall_watchdog_timer", None)
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
        app._ui_stall_watchdog_timer = None
        state = "disabled"
    else:
        app._start_ui_stall_watchdog()
        state = f"{ms:g}ms"

    app.notify(f"UI stall watchdog {state}")


register_command_handler(_handle_watchdog_command)
