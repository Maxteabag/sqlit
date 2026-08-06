"""CLI handlers for the `sqlit alerts` subcommand."""

from __future__ import annotations

from typing import Any

from sqlit.domains.query.app.alerts import (
    CONNECTION_ALERT_OPTION,
    DATABASE_ALERT_SETTING,
    GLOBAL_ALERT_SETTING,
    AlertMode,
    format_alert_mode,
    make_db_alert_key,
    parse_alert_mode,
)
from sqlit.shared.app.runtime import RuntimeConfig
from sqlit.shared.app.services import AppServices, build_app_services


def _services(services: AppServices | None) -> AppServices:
    return services or build_app_services(RuntimeConfig.from_env())


def _format(value: Any) -> str:
    parsed = parse_alert_mode(value)
    return format_alert_mode(parsed) if parsed is not None else f"<invalid: {value!r}>"


def _resolve_global_mode(services: AppServices) -> AlertMode:
    raw = services.settings_store.get(GLOBAL_ALERT_SETTING)
    parsed = parse_alert_mode(raw)
    return parsed if parsed is not None else AlertMode.OFF


def _resolve_db_overrides(services: AppServices) -> dict[str, Any]:
    raw = services.settings_store.get(DATABASE_ALERT_SETTING)
    return dict(raw) if isinstance(raw, dict) else {}


def cmd_alerts_list(args: Any, *, services: AppServices | None = None) -> int:
    """Show global, per-connection, and per-database alert overrides."""
    services = _services(services)

    global_mode = _resolve_global_mode(services)
    print(f"Global: {format_alert_mode(global_mode)}")

    connections = services.connection_store.load_all(load_credentials=False)
    conn_overrides = [
        (c.name, c.get_option(CONNECTION_ALERT_OPTION))
        for c in connections
        if c.get_option(CONNECTION_ALERT_OPTION) is not None
    ]
    if conn_overrides:
        print("\nPer-connection:")
        for name, value in conn_overrides:
            print(f"  {name:<30} {_format(value)}")
    else:
        print("\nPer-connection: (none)")

    db_overrides = _resolve_db_overrides(services)
    if db_overrides:
        print("\nPer-database:")
        for key, value in sorted(db_overrides.items()):
            print(f"  {key:<30} {_format(value)}")
    else:
        print("\nPer-database: (none)")
    return 0


def cmd_alerts_set(args: Any, *, services: AppServices | None = None) -> int:
    """Set an alert mode at the requested scope."""
    services = _services(services)

    mode = parse_alert_mode(getattr(args, "mode", None))
    if mode is None:
        print(f"Error: invalid mode '{getattr(args, 'mode', '')}'. Use off, delete, or write.")
        return 1

    connection = getattr(args, "connection", None)
    database = getattr(args, "database", None)

    if database and not connection:
        print("Error: --database requires --connection.")
        return 1

    if not connection:
        services.settings_store.set(GLOBAL_ALERT_SETTING, int(mode))
        print(f"Global alerts set to {format_alert_mode(mode)}")
        return 0

    connections = services.connection_store.load_all(load_credentials=False)
    target = next((c for c in connections if c.name == connection), None)
    if target is None:
        print(f"Error: Connection '{connection}' not found.")
        return 1

    if database:
        overrides = _resolve_db_overrides(services)
        overrides[make_db_alert_key(connection, database)] = format_alert_mode(mode)
        services.settings_store.set(DATABASE_ALERT_SETTING, overrides)
        print(
            f"Alerts for database '{database}' on '{connection}' set to {format_alert_mode(mode)}"
        )
        return 0

    target.set_option(CONNECTION_ALERT_OPTION, format_alert_mode(mode))
    services.connection_store.save_all(connections)
    print(f"Connection '{connection}' alerts set to {format_alert_mode(mode)}")
    return 0


def cmd_alerts_unset(args: Any, *, services: AppServices | None = None) -> int:
    """Clear an alert override at the requested scope."""
    services = _services(services)

    connection = getattr(args, "connection", None)
    database = getattr(args, "database", None)

    if database and not connection:
        print("Error: --database requires --connection.")
        return 1

    if not connection:
        services.settings_store.delete(GLOBAL_ALERT_SETTING)
        print("Global alert mode cleared (defaults to off)")
        return 0

    if database:
        overrides = _resolve_db_overrides(services)
        key = make_db_alert_key(connection, database)
        if key not in overrides:
            print(f"No alert override for database '{database}' on '{connection}'.")
            return 0
        overrides.pop(key)
        services.settings_store.set(DATABASE_ALERT_SETTING, overrides)
        print(f"Alert override for database '{database}' on '{connection}' cleared")
        return 0

    connections = services.connection_store.load_all(load_credentials=False)
    target = next((c for c in connections if c.name == connection), None)
    if target is None:
        print(f"Error: Connection '{connection}' not found.")
        return 1
    if CONNECTION_ALERT_OPTION not in target.options:
        print(f"Connection '{connection}' has no alert override.")
        return 0
    target.options.pop(CONNECTION_ALERT_OPTION, None)
    services.connection_store.save_all(connections)
    print(f"Alert override for connection '{connection}' cleared")
    return 0
