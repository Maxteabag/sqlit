"""Integration test: drive _maybe_confirm_query through each scope.

This exercises the actual code path in
``sqlit/domains/query/ui/mixins/query_execution.py`` rather than the
isolated resolver helper.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.query.app.alerts import (
    CONNECTION_ALERT_OPTION,
    DATABASE_ALERT_SETTING,
    AlertMode,
    make_db_alert_key,
)
from sqlit.domains.query.ui.mixins.query_execution import QueryExecutionMixin


class _Runtime:
    def __init__(self, mode: int = 0) -> None:
        self.query_alert_mode = mode


class _Settings:
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data: dict[str, Any] = dict(data or {})

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


@dataclass
class _Services:
    runtime: _Runtime = field(default_factory=_Runtime)
    settings_store: _Settings = field(default_factory=_Settings)


class _Host:
    """Bare host that satisfies the attribute surface _maybe_confirm_query touches."""

    def __init__(
        self,
        *,
        runtime_mode: int = 0,
        connection: ConnectionConfig | None = None,
        database: str | None = None,
        db_overrides: dict[str, Any] | None = None,
    ) -> None:
        self.services = _Services(
            runtime=_Runtime(runtime_mode),
            settings_store=_Settings(
                {DATABASE_ALERT_SETTING: db_overrides} if db_overrides else None
            ),
        )
        self.current_config = connection
        self._database = database
        self.pushed_screens: list[Any] = []
        self.notifications: list[tuple[str, str | None]] = []

    def _get_effective_database(self) -> str | None:
        return self._database

    def push_screen(self, screen: Any, callback: Any) -> None:
        self.pushed_screens.append((screen, callback))

    def notify(self, msg: str, *, severity: str | None = None, **kwargs: Any) -> None:
        self.notifications.append((msg, severity))


def _confirm(host: _Host, sql: str) -> tuple[bool, _Host]:
    """Invoke the real _maybe_confirm_query; return (proceed_called, host)."""
    called = {"v": False}

    def _proceed() -> None:
        called["v"] = True

    QueryExecutionMixin._maybe_confirm_query(host, sql, _proceed)  # type: ignore[arg-type]
    return called["v"], host


# ---------------------------------------------------------------------------
# Hierarchy: each scope shadows the looser one


def test_global_off_skips_confirmation() -> None:
    host = _Host(runtime_mode=int(AlertMode.OFF))
    proceeded, host = _confirm(host, "DELETE FROM users")
    assert proceeded is True
    assert host.pushed_screens == []


def test_global_delete_triggers_confirm_for_delete() -> None:
    host = _Host(runtime_mode=int(AlertMode.DELETE))
    proceeded, host = _confirm(host, "DELETE FROM users")
    assert proceeded is False  # waiting for confirm
    assert len(host.pushed_screens) == 1


def test_global_delete_does_not_prompt_on_pure_select() -> None:
    host = _Host(runtime_mode=int(AlertMode.DELETE))
    proceeded, host = _confirm(host, "SELECT 1")
    assert proceeded is True
    assert host.pushed_screens == []


def test_connection_override_relaxes_stricter_global() -> None:
    """Global = delete (confirm on delete) but connection sets off → skip."""
    conn = ConnectionConfig(name="prod")
    conn.set_option(CONNECTION_ALERT_OPTION, "off")
    host = _Host(runtime_mode=int(AlertMode.DELETE), connection=conn)
    proceeded, host = _confirm(host, "DELETE FROM users")
    assert proceeded is True, "connection-level off should override global delete"
    assert host.pushed_screens == []


def test_connection_override_tightens_looser_global() -> None:
    """Global = off but a specific connection wants write-level alerts."""
    conn = ConnectionConfig(name="prod")
    conn.set_option(CONNECTION_ALERT_OPTION, "write")
    host = _Host(runtime_mode=int(AlertMode.OFF), connection=conn)
    proceeded, host = _confirm(host, "UPDATE users SET active = 0")
    assert proceeded is False
    assert len(host.pushed_screens) == 1


def test_database_override_beats_connection_and_global() -> None:
    """Strictest scope (db) takes precedence."""
    conn = ConnectionConfig(name="prod")
    conn.set_option(CONNECTION_ALERT_OPTION, "off")
    host = _Host(
        runtime_mode=int(AlertMode.OFF),
        connection=conn,
        database="warehouse",
        db_overrides={make_db_alert_key("prod", "warehouse"): "delete"},
    )
    proceeded, host = _confirm(host, "DELETE FROM events")
    assert proceeded is False
    assert len(host.pushed_screens) == 1


def test_database_override_can_silence_strict_global() -> None:
    """Db scope can also relax a strict global setting."""
    conn = ConnectionConfig(name="prod")
    host = _Host(
        runtime_mode=int(AlertMode.WRITE),
        connection=conn,
        database="sandbox",
        db_overrides={make_db_alert_key("prod", "sandbox"): "off"},
    )
    proceeded, host = _confirm(host, "INSERT INTO t VALUES (1)")
    assert proceeded is True
    assert host.pushed_screens == []


def test_db_override_only_matches_its_own_database() -> None:
    """An override keyed at db A must not apply when active db is B."""
    conn = ConnectionConfig(name="prod")
    host = _Host(
        runtime_mode=int(AlertMode.OFF),
        connection=conn,
        database="reports",  # active db is reports
        db_overrides={make_db_alert_key("prod", "warehouse"): "delete"},
    )
    proceeded, host = _confirm(host, "DELETE FROM stuff")
    # No matching db override and no connection override and global is off.
    assert proceeded is True


def test_db_override_only_matches_its_own_connection() -> None:
    """An override keyed at connection A must not apply when active conn is B."""
    conn = ConnectionConfig(name="other")
    host = _Host(
        runtime_mode=int(AlertMode.OFF),
        connection=conn,
        database="warehouse",
        db_overrides={make_db_alert_key("prod", "warehouse"): "delete"},
    )
    proceeded, host = _confirm(host, "DELETE FROM stuff")
    assert proceeded is True
