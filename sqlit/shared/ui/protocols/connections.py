"""Protocols for connection state and behaviors."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from textual.timer import Timer
    from sqlit.domains.connections.app.session import ConnectionSession
    from sqlit.domains.connections.domain.config import ConnectionConfig
    from sqlit.domains.connections.providers.model import DatabaseProvider
    from sqlit.shared.ui.spinner import Spinner


class ConnectionStateProtocol(Protocol):
    services: Any
    connections: list[ConnectionConfig]
    current_connection: Any | None
    current_config: ConnectionConfig | None
    current_provider: DatabaseProvider | None
    current_ssh_tunnel: Any
    _direct_connection_config: ConnectionConfig | None
    _connecting_config: ConnectionConfig | None
    _connection_attempt_id: int
    _connect_spinner: Spinner | None
    _connect_spinner_index: int
    _connect_spinner_timer: Timer | None

    _session: ConnectionSession | None
    _connection_failed: bool


class ConnectionActionsProtocol(Protocol):
    def _update_connecting_indicator(self) -> None:
        ...

    def _set_connecting_state(self, config: ConnectionConfig | None, refresh: bool = True) -> None:
        ...

    def _select_connected_node(self) -> None:
        ...

    def _disconnect_silent(self) -> None:
        ...

    def connect_to_server(self, config: ConnectionConfig) -> None:
        ...

    def _set_connection_screen_footer(self) -> None:
        ...

    def _wrap_connection_result(self, result: tuple[Any, ...] | None) -> None:
        ...

    def call_next(self, *args: Any, **kwargs: Any) -> None:
        ...

    def handle_connection_result(self, result: tuple[Any, ...] | None) -> None:
        ...

    def _do_delete_connection(self, config: ConnectionConfig) -> None:
        ...

    def _handle_connection_picker_result(self, result: str | None) -> None:
        ...

    def _populate_credentials_if_missing(self, config: ConnectionConfig) -> None:
        ...

    def _connect_with_db_password_check(self, config: ConnectionConfig) -> None:
        ...

    def _do_connect(self, config: ConnectionConfig) -> None:
        ...

    def _start_connect_spinner(self) -> None:
        ...

    def _stop_connect_spinner(self) -> None:
        ...

    def _on_connect_spinner_tick(self) -> None:
        ...

    def _get_connection_config_from_data(self, data: Any) -> ConnectionConfig | None:
        ...

    def action_new_connection(self) -> None:
        ...

    def _get_connection_config_from_node(self, node: Any) -> ConnectionConfig | None:
        ...

    def _get_connection_result_registry(self) -> Any:
        ...


class ConnectionsProtocol(ConnectionStateProtocol, ConnectionActionsProtocol, Protocol):
    """Composite protocol for connection-related mixins."""

    pass
