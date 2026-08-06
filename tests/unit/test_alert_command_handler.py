"""Tests for the :alert shell command handler."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.query.app.alerts import (
    CONNECTION_ALERT_OPTION,
    DATABASE_ALERT_SETTING,
    GLOBAL_ALERT_SETTING,
    AlertMode,
    make_db_alert_key,
)
from sqlit.domains.shell.app.commands.alert import _handle_alert_command


class _FakeRuntime:
    def __init__(self, mode: int = 0) -> None:
        self.query_alert_mode = mode


class _FakeSettingsStore:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    def load_all(self) -> dict:
        return dict(self.data)

    def save_all(self, settings: dict) -> None:
        self.data = dict(settings)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def delete(self, key: str) -> bool:
        return self.data.pop(key, None) is not None


class _FakeConnectionStore:
    def __init__(self) -> None:
        self.saved: list[ConnectionConfig] = []

    def save_all(self, connections: list[ConnectionConfig]) -> None:
        self.saved = list(connections)

    def load_all(self, load_credentials: bool = True) -> list[ConnectionConfig]:
        return list(self.saved)


@dataclass
class _FakeServices:
    runtime: _FakeRuntime = field(default_factory=_FakeRuntime)
    settings_store: _FakeSettingsStore = field(default_factory=_FakeSettingsStore)
    connection_store: _FakeConnectionStore = field(default_factory=_FakeConnectionStore)


class _FakeApp:
    """Minimal duck-typed app stand-in used by _handle_alert_command."""

    def __init__(
        self,
        *,
        current_config: ConnectionConfig | None = None,
        database: str | None = None,
        connections: list[ConnectionConfig] | None = None,
    ) -> None:
        self.services = _FakeServices()
        self.current_config = current_config
        self._database = database
        self.connections = list(connections or [])
        self.notifications: list[tuple[str, str | None]] = []

    def notify(self, message: str, *, severity: str | None = None) -> None:
        self.notifications.append((message, severity))

    def _get_effective_database(self) -> str | None:
        return self._database

    # Helpers for assertions.
    def last_notification(self) -> tuple[str, str | None]:
        assert self.notifications, "expected at least one notification"
        return self.notifications[-1]


# ---------------------------------------------------------------------------
# Command routing


def test_handler_rejects_unrelated_command() -> None:
    app = _FakeApp()
    assert _handle_alert_command(app, "theme", ["dark"]) is False
    assert _handle_alert_command(app, "alert", []) is True
    assert _handle_alert_command(app, "alerts", []) is True


# ---------------------------------------------------------------------------
# Implicit-global form (back-compat: `:alert delete`)


def test_implicit_global_set() -> None:
    app = _FakeApp()
    _handle_alert_command(app, "alert", ["delete"])
    assert app.services.runtime.query_alert_mode == int(AlertMode.DELETE)
    assert app.services.settings_store.get(GLOBAL_ALERT_SETTING) == int(AlertMode.DELETE)


def test_implicit_global_invalid_warns() -> None:
    app = _FakeApp()
    _handle_alert_command(app, "alert", ["garbage"])
    msg, severity = app.last_notification()
    assert "Usage" in msg
    assert severity == "warning"


# ---------------------------------------------------------------------------
# Explicit scopes


def test_global_scope_set_and_unset() -> None:
    app = _FakeApp()
    _handle_alert_command(app, "alert", ["global", "write"])
    assert app.services.runtime.query_alert_mode == int(AlertMode.WRITE)

    _handle_alert_command(app, "alert", ["global", "unset"])
    assert app.services.runtime.query_alert_mode == int(AlertMode.OFF)


def test_connection_scope_requires_active_connection() -> None:
    app = _FakeApp(current_config=None)
    _handle_alert_command(app, "alert", ["connection", "delete"])
    msg, severity = app.last_notification()
    assert "No active connection" in msg
    assert severity == "warning"


def test_connection_scope_set_writes_to_options_and_persists() -> None:
    conn = ConnectionConfig(name="prod")
    app = _FakeApp(current_config=conn, connections=[conn])
    _handle_alert_command(app, "alert", ["connection", "delete"])
    assert conn.get_option(CONNECTION_ALERT_OPTION) == "delete"
    # Saved connections were persisted because it was a known one.
    assert app.services.connection_store.saved[0].get_option(CONNECTION_ALERT_OPTION) == "delete"


def test_connection_scope_temp_connection_not_persisted() -> None:
    """A connection not in app.connections (e.g. ad-hoc) should not be saved."""
    conn = ConnectionConfig(name="temp")
    app = _FakeApp(current_config=conn, connections=[])  # not in list
    _handle_alert_command(app, "alert", ["connection", "write"])
    assert conn.get_option(CONNECTION_ALERT_OPTION) == "write"
    # No persistence call happened.
    assert app.services.connection_store.saved == []


def test_connection_scope_unset_clears_option() -> None:
    conn = ConnectionConfig(name="prod")
    conn.set_option(CONNECTION_ALERT_OPTION, "delete")
    app = _FakeApp(current_config=conn, connections=[conn])
    _handle_alert_command(app, "alert", ["connection", "unset"])
    assert CONNECTION_ALERT_OPTION not in conn.options


def test_database_scope_requires_database() -> None:
    conn = ConnectionConfig(name="prod")
    app = _FakeApp(current_config=conn, database=None, connections=[conn])
    _handle_alert_command(app, "alert", ["database", "delete"])
    msg, severity = app.last_notification()
    assert "No active database" in msg
    assert severity == "warning"


def test_database_scope_set_writes_to_settings() -> None:
    conn = ConnectionConfig(name="prod")
    app = _FakeApp(current_config=conn, database="warehouse", connections=[conn])
    _handle_alert_command(app, "alert", ["database", "write"])
    overrides = app.services.settings_store.get(DATABASE_ALERT_SETTING)
    assert overrides == {make_db_alert_key("prod", "warehouse"): "write"}


def test_database_scope_unset_removes_key() -> None:
    conn = ConnectionConfig(name="prod")
    app = _FakeApp(current_config=conn, database="warehouse", connections=[conn])
    app.services.settings_store.set(
        DATABASE_ALERT_SETTING,
        {make_db_alert_key("prod", "warehouse"): "delete"},
    )
    _handle_alert_command(app, "alert", ["database", "unset"])
    overrides = app.services.settings_store.get(DATABASE_ALERT_SETTING)
    assert overrides == {}


def test_db_scope_alias_maps_to_database() -> None:
    conn = ConnectionConfig(name="prod")
    app = _FakeApp(current_config=conn, database="warehouse", connections=[conn])
    _handle_alert_command(app, "alert", ["db", "delete"])
    overrides = app.services.settings_store.get(DATABASE_ALERT_SETTING)
    assert overrides == {make_db_alert_key("prod", "warehouse"): "delete"}


# ---------------------------------------------------------------------------
# Status / inspection


def test_status_with_no_args_shows_all_scopes() -> None:
    conn = ConnectionConfig(name="prod")
    conn.set_option(CONNECTION_ALERT_OPTION, "delete")
    app = _FakeApp(current_config=conn, database="warehouse", connections=[conn])
    app.services.runtime.query_alert_mode = int(AlertMode.WRITE)
    app.services.settings_store.set(
        DATABASE_ALERT_SETTING,
        {make_db_alert_key("prod", "warehouse"): "off"},
    )

    _handle_alert_command(app, "alert", [])
    msg, _ = app.last_notification()
    # Effective mode is "off" because database scope wins.
    assert "effective: off (from database)" in msg
    assert "global: write" in msg
    assert "connection: delete" in msg
    assert "database: off" in msg


def test_status_with_scope_only_reports_that_scope() -> None:
    conn = ConnectionConfig(name="prod")
    app = _FakeApp(current_config=conn, connections=[conn])
    _handle_alert_command(app, "alert", ["connection"])
    msg, _ = app.last_notification()
    assert "Connection alert override: unset" in msg


# ---------------------------------------------------------------------------
# Invalid input


def test_invalid_mode_warns() -> None:
    conn = ConnectionConfig(name="prod")
    app = _FakeApp(current_config=conn, connections=[conn])
    _handle_alert_command(app, "alert", ["connection", "supernuke"])
    msg, severity = app.last_notification()
    assert "Usage" in msg
    assert severity == "warning"


def test_clear_alias_unset_alias_default_alias() -> None:
    conn = ConnectionConfig(name="prod")
    conn.set_option(CONNECTION_ALERT_OPTION, "delete")
    app = _FakeApp(current_config=conn, connections=[conn])
    _handle_alert_command(app, "alert", ["connection", "clear"])
    assert CONNECTION_ALERT_OPTION not in conn.options

    conn.set_option(CONNECTION_ALERT_OPTION, "delete")
    _handle_alert_command(app, "alert", ["connection", "default"])
    assert CONNECTION_ALERT_OPTION not in conn.options
