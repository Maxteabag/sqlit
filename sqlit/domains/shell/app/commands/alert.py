"""Query alert mode command handlers."""

from __future__ import annotations

from typing import Any

from sqlit.domains.query.app.alerts import (
    CONNECTION_ALERT_OPTION,
    DATABASE_ALERT_SETTING,
    GLOBAL_ALERT_SETTING,
    AlertMode,
    format_alert_mode,
    lookup_database_override,
    make_db_alert_key,
    parse_alert_mode,
    resolve_alert_mode,
)

from .router import register_command_handler


_USAGE = (
    "Usage: :alert [global|connection|database] off|delete|write|unset"
)


def _handle_alert_command(app: Any, cmd: str, args: list[str]) -> bool:
    if cmd not in {"alert", "alerts"}:
        return False

    if not args:
        _show_alert_status(app)
        return True

    scope, mode_token = _parse_scope_and_mode(args)
    if scope is None:
        app.notify(_USAGE, severity="warning")
        return True

    if mode_token is None:
        # Show current value for the named scope.
        _show_scope_status(app, scope)
        return True

    if mode_token in {"unset", "clear", "default"}:
        _unset_scope(app, scope)
        return True

    mode = parse_alert_mode(mode_token)
    if mode is None:
        app.notify(_USAGE, severity="warning")
        return True

    _set_scope(app, scope, mode)
    return True


def _parse_scope_and_mode(args: list[str]) -> tuple[str | None, str | None]:
    first = args[0].lower()
    if first in {"global", "connection", "database", "db"}:
        scope = "database" if first == "db" else first
        mode_token = args[1].lower() if len(args) > 1 else None
        return scope, mode_token
    # No explicit scope -> implicit global.
    return "global", first


def _show_alert_status(app: Any) -> None:
    global_mode, connection_value, database_value, effective_mode, source = _collect_state(app)
    parts = [f"effective: {format_alert_mode(effective_mode)} (from {source})"]
    parts.append(f"global: {format_alert_mode(global_mode)}")
    if connection_value is not None:
        parts.append(f"connection: {_format_value(connection_value)}")
    else:
        parts.append("connection: unset")
    if database_value is not None:
        parts.append(f"database: {_format_value(database_value)}")
    else:
        parts.append("database: unset")
    app.notify(" | ".join(parts))


def _show_scope_status(app: Any, scope: str) -> None:
    global_mode, connection_value, database_value, _, _ = _collect_state(app)
    if scope == "global":
        app.notify(f"Global alert mode: {format_alert_mode(global_mode)}")
        return
    if scope == "connection":
        if connection_value is None:
            app.notify("Connection alert override: unset (falls back to global)")
            return
        app.notify(f"Connection alert override: {_format_value(connection_value)}")
        return
    if scope == "database":
        if database_value is None:
            app.notify("Database alert override: unset (falls back to connection/global)")
            return
        app.notify(f"Database alert override: {_format_value(database_value)}")


def _set_scope(app: Any, scope: str, mode: AlertMode) -> None:
    if scope == "global":
        _set_global(app, mode)
        return
    if scope == "connection":
        _set_connection(app, mode)
        return
    if scope == "database":
        _set_database(app, mode)


def _unset_scope(app: Any, scope: str) -> None:
    if scope == "global":
        # "Unset" on global means OFF — there's no level above it.
        _set_global(app, AlertMode.OFF)
        return
    if scope == "connection":
        _clear_connection(app)
        return
    if scope == "database":
        _clear_database(app)


# ---------------------------------------------------------------------------
# Global scope


def _set_global(app: Any, mode: AlertMode) -> None:
    app.services.runtime.query_alert_mode = int(mode)
    try:
        app.services.settings_store.set(GLOBAL_ALERT_SETTING, int(mode))
    except Exception:
        pass
    app.notify(f"Global query alerts set to {format_alert_mode(mode)}")


# ---------------------------------------------------------------------------
# Connection scope


def _set_connection(app: Any, mode: AlertMode) -> None:
    config = getattr(app, "current_config", None)
    if config is None:
        app.notify("No active connection — connect first to set a connection alert", severity="warning")
        return
    config.set_option(CONNECTION_ALERT_OPTION, format_alert_mode(mode))
    _persist_connection(app, config)
    app.notify(f"Connection '{config.name}' alerts set to {format_alert_mode(mode)}")


def _clear_connection(app: Any) -> None:
    config = getattr(app, "current_config", None)
    if config is None:
        app.notify("No active connection — connect first to clear a connection alert", severity="warning")
        return
    if CONNECTION_ALERT_OPTION not in config.options:
        app.notify(f"Connection '{config.name}' has no alert override")
        return
    config.options.pop(CONNECTION_ALERT_OPTION, None)
    _persist_connection(app, config)
    app.notify(f"Connection '{config.name}' alert override cleared")


def _persist_connection(app: Any, config: Any) -> None:
    """Save the connection back to the store, if it's a saved one."""
    try:
        connections = list(getattr(app, "connections", None) or [])
    except Exception:
        connections = []
    if not connections:
        return
    if not any(getattr(c, "name", None) == getattr(config, "name", None) for c in connections):
        # Temporary / direct connection — keep in memory only.
        return
    try:
        app.services.connection_store.save_all(connections)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Database scope


def _set_database(app: Any, mode: AlertMode) -> None:
    config = getattr(app, "current_config", None)
    if config is None:
        app.notify("No active connection — connect first to set a database alert", severity="warning")
        return
    database = _current_database(app)
    if not database:
        app.notify("No active database — open a database first to set a database alert", severity="warning")
        return
    overrides = _load_db_overrides(app)
    overrides[make_db_alert_key(config.name, database)] = format_alert_mode(mode)
    _save_db_overrides(app, overrides)
    app.notify(f"Database '{database}' (on '{config.name}') alerts set to {format_alert_mode(mode)}")


def _clear_database(app: Any) -> None:
    config = getattr(app, "current_config", None)
    if config is None:
        app.notify("No active connection — connect first to clear a database alert", severity="warning")
        return
    database = _current_database(app)
    if not database:
        app.notify("No active database — open a database first to clear a database alert", severity="warning")
        return
    overrides = _load_db_overrides(app)
    key = make_db_alert_key(config.name, database)
    if key not in overrides:
        app.notify(f"Database '{database}' has no alert override")
        return
    overrides.pop(key, None)
    _save_db_overrides(app, overrides)
    app.notify(f"Database '{database}' alert override cleared")


def _current_database(app: Any) -> str | None:
    get_db = getattr(app, "_get_effective_database", None)
    if not callable(get_db):
        return None
    try:
        value = get_db()
    except Exception:
        return None
    return str(value) if value else None


def _load_db_overrides(app: Any) -> dict[str, Any]:
    try:
        raw = app.services.settings_store.get(DATABASE_ALERT_SETTING)
    except Exception:
        return {}
    return dict(raw) if isinstance(raw, dict) else {}


def _save_db_overrides(app: Any, overrides: dict[str, Any]) -> None:
    try:
        app.services.settings_store.set(DATABASE_ALERT_SETTING, overrides)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Status collection


def _collect_state(
    app: Any,
) -> tuple[AlertMode, Any, Any, AlertMode, str]:
    raw_global = getattr(app.services.runtime, "query_alert_mode", 0) or 0
    try:
        global_mode = AlertMode(int(raw_global))
    except (TypeError, ValueError):
        global_mode = AlertMode.OFF

    config = getattr(app, "current_config", None)
    connection_value = None
    if config is not None:
        connection_value = config.get_option(CONNECTION_ALERT_OPTION)

    database_value = None
    database = _current_database(app)
    overrides = _load_db_overrides(app)
    connection_name = getattr(config, "name", None) if config is not None else None
    database_value = lookup_database_override(overrides, connection_name, database)

    effective_mode, source = resolve_alert_mode(
        global_mode=int(global_mode),
        connection_option=connection_value,
        database_override=database_value,
    )
    return global_mode, connection_value, database_value, effective_mode, source


def _format_value(value: Any) -> str:
    parsed = parse_alert_mode(value)
    if parsed is None:
        return str(value)
    return format_alert_mode(parsed)


register_command_handler(_handle_alert_command)
