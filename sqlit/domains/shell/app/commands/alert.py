"""Query alert mode command handlers."""

from __future__ import annotations

from typing import Any

from sqlit.domains.query.app.alerts import AlertMode, format_alert_mode, parse_alert_mode

from .router import register_command_handler


def _handle_alert_command(app: Any, cmd: str, args: list[str]) -> bool:
    if cmd not in {"alert", "alerts"}:
        return False

    value = args[0].lower() if args else ""
    if not value:
        _show_alert_status(app)
        return True

    mode = parse_alert_mode(value)
    if mode is None:
        app.notify("Usage: :alert off|delete|write", severity="warning")
        return True

    _set_alert_mode(app, mode)
    return True


def _show_alert_status(app: Any) -> None:
    mode = _get_alert_mode(app)
    label = format_alert_mode(mode)
    app.notify(f"Query alerts: {label}")


def _set_alert_mode(app: Any, mode: AlertMode) -> None:
    app.services.runtime.query_alert_mode = int(mode)
    try:
        app.services.settings_store.set("query_alert_mode", int(mode))
    except Exception:
        pass
    app.notify(f"Query alerts set to {format_alert_mode(mode)}")


def _get_alert_mode(app: Any) -> AlertMode:
    raw = getattr(app.services.runtime, "query_alert_mode", 0) or 0
    return AlertMode(int(raw))


register_command_handler(_handle_alert_command)
