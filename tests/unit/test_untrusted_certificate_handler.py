"""Trusting an unverifiable SQL Server certificate from the connection error."""

from __future__ import annotations

from typing import Any

from sqlit.domains.connections.ui.connection_error_handlers import handle_connection_error
from tests.helpers import ConnectionConfig

ODBC_SELF_SIGNED = (
    "[Microsoft][ODBC Driver 18 for SQL Server]SSL Provider: "
    "[error:0A000086:SSL routines::certificate verify failed:self-signed certificate]"
)


class _Store:
    def __init__(self) -> None:
        self.saved: list[Any] = []

    def save_one(self, config: Any, previous_name: str | None = None) -> None:
        self.saved.append(config)


class _Services:
    def __init__(self) -> None:
        self.connection_store = _Store()


class _App:
    def __init__(self, connections: list[Any]) -> None:
        self.services = _Services()
        self.connections = connections
        self.screens: list[tuple[Any, Any]] = []
        self.connected: list[Any] = []

    def push_screen(self, screen: Any, callback: Any = None) -> None:
        self.screens.append((screen, callback))

    def connect_to_server(self, config: Any) -> None:
        self.connected.append(config)

    def notify(self, *args: Any, **kwargs: Any) -> None:
        pass


def _config() -> ConnectionConfig:
    return ConnectionConfig(
        name="prod", db_type="mssql", server="sql.corp.local", port="1433",
        database="master", username="sa", password="secret", options={"auth_type": "sql"},
    )


def test_confirming_trusts_saves_and_reconnects():
    config = _config()
    app = _App([config])

    assert handle_connection_error(app, RuntimeError(ODBC_SELF_SIGNED), config)
    screen, callback = app.screens[-1]
    assert type(screen).__name__ == "ConfirmScreen"

    callback(True)

    from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter

    conn_str = SQLServerAdapter().build_connection_string(config)
    assert "Encrypt=yes;TrustServerCertificate=yes;" in conn_str
    assert app.services.connection_store.saved == [config]
    assert app.connected == [config]


def test_declining_changes_nothing():
    config = _config()
    app = _App([config])

    handle_connection_error(app, RuntimeError(ODBC_SELF_SIGNED), config)
    app.screens[-1][1](False)

    assert config.get_option("tls_mode") is None
    assert app.services.connection_store.saved == []
    assert app.connected == []
