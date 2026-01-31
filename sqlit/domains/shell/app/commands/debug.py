"""Debug event logging command handlers."""

from __future__ import annotations

from typing import Any

from sqlit.shared.core.debug_events import DebugEvent, format_debug_data

from .router import register_command_handler


def _handle_debug_command(app: Any, cmd: str, args: list[str]) -> bool:
    if cmd not in {"debug", "dbg"}:
        return False

    value = args[0].lower() if args else ""
    if value in {"on", "enable", "enabled", "1", "true", "yes"}:
        _set_debug_enabled(app, True)
        return True
    if value in {"off", "disable", "disabled", "0", "false", "no"}:
        _set_debug_enabled(app, False)
        return True
    if value == "list":
        _show_debug_events(app)
        return True
    if value == "clear":
        _clear_debug_events(app)
        return True
    if not value:
        _show_debug_status(app)
        return True

    app.notify("Unknown debug command. Try :debug on|off|list|clear", severity="warning")
    return True


def _set_debug_enabled(app: Any, enabled: bool) -> None:
    setter = getattr(app, "_set_debug_events_enabled", None)
    if callable(setter):
        setter(enabled)
    else:
        app._debug_events_enabled = bool(enabled)

    # Persist the setting across sessions
    try:
        services = getattr(app, "services", None)
        if services:
            store = getattr(services, "settings_store", None)
            if store:
                store.set("debug_events_enabled", enabled)
    except Exception:
        pass

    path = getattr(app, "_debug_event_log_path", None)
    suffix = f" (log: {path})" if path else ""
    state = "enabled" if enabled else "disabled"
    app.notify(f"Debug logging {state}{suffix}")


def _show_debug_status(app: Any) -> None:
    enabled = bool(getattr(app, "_debug_events_enabled", False))
    history = getattr(app, "_debug_event_history", [])
    count = len(history) if isinstance(history, list) else 0
    path = getattr(app, "_debug_event_log_path", None)
    suffix = f" (log: {path})" if path else ""
    state = "enabled" if enabled else "disabled"
    app.notify(f"Debug logging {state}, events={count}{suffix}")


def _show_debug_events(app: Any) -> None:
    events = getattr(app, "_debug_event_history", [])
    if not events:
        app.notify("No debug events recorded")
        return
    columns = ["Time", "Category", "Event", "Details"]
    rows: list[tuple[str, str, str, str]] = []
    for event in events[-50:]:
        if isinstance(event, DebugEvent):
            rows.append((event.iso, event.category, event.name, format_debug_data(event.data)))
        else:
            rows.append(("", "", str(event), ""))
    if hasattr(app, "_replace_results_table"):
        app._replace_results_table(columns, rows)
    path = getattr(app, "_debug_event_log_path", None)
    if path:
        app.notify(f"Debug log: {path}")


def _clear_debug_events(app: Any) -> None:
    try:
        history = getattr(app, "_debug_event_history", None)
        if isinstance(history, list):
            history.clear()
    except Exception:
        pass

    path = getattr(app, "_debug_event_log_path", None)
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
            app.notify("Failed to clear debug log", severity="warning")
            return
    app.notify("Debug log cleared")


register_command_handler(_handle_debug_command)
