"""Connection workflow helpers for UI mixins."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.domain.passwords import needs_db_password, needs_ssh_password
from sqlit.shared.app import AppServices


class ConnectionPrompter(Protocol):
    """Interface for prompting the user for missing credentials."""

    def prompt_ssh_password(self, config: ConnectionConfig, on_done: Any) -> None: ...

    def prompt_db_password(self, config: ConnectionConfig, on_done: Any) -> None: ...


@dataclass
class ConnectionFlow:
    """Handle credential checks and prompt sequencing for connections."""

    services: AppServices
    connection_manager: Any | None = None
    prompter: ConnectionPrompter | None = None
    emit_debug: Callable[..., None] | None = None

    def _emit_debug(self, name: str, **data: Any) -> None:
        if not self.emit_debug:
            return
        try:
            self.emit_debug(name, **data)
        except Exception:
            pass

    def populate_credentials_if_missing(self, config: ConnectionConfig) -> None:
        """Populate missing credentials from the credentials service."""
        if self.connection_manager is not None:
            self.connection_manager.populate_credentials(config)
            return
        endpoint = config.tcp_endpoint
        if endpoint and endpoint.password is not None and (not config.tunnel or config.tunnel.password is not None):
            return
        service = self.services.credentials_service
        if endpoint and endpoint.password is None:
            password = service.get_password(config.name)
            if password is not None:
                endpoint.password = password
        if config.tunnel and config.tunnel.password is None:
            ssh_password = service.get_ssh_password(config.name)
            if ssh_password is not None:
                config.tunnel.password = ssh_password

    def start(self, config: ConnectionConfig, on_ready: Any) -> None:
        """Start the connection flow, prompting for missing passwords as needed."""
        self.populate_credentials_if_missing(config)
        self._emit_debug(
            "connection_flow.start",
            connection=config.name,
            db_type=str(config.db_type),
            needs_ssh=needs_ssh_password(config),
            needs_db=needs_db_password(config),
            has_db_password=bool(config.tcp_endpoint and config.tcp_endpoint.password is not None),
            has_ssh_password=bool(config.tunnel and config.tunnel.password is not None),
        )

        if needs_ssh_password(config):
            if not self.prompter:
                self._emit_debug("connection_flow.ssh_prompt_missing", connection=config.name)
                return

            def on_ssh_password(password: str | None) -> None:
                self._emit_debug(
                    "connection_flow.ssh_password",
                    connection=config.name,
                    provided=password is not None,
                    value_len=len(password) if password is not None else 0,
                )
                if password is None:
                    return
                temp_config = config.with_tunnel(password=password)
                self._with_db_password(temp_config, on_ready)

            self.prompter.prompt_ssh_password(config, on_ssh_password)
            return

        self._with_db_password(config, on_ready)

    def _with_db_password(self, config: ConnectionConfig, on_ready: Any) -> None:
        if needs_db_password(config):
            if not self.prompter:
                self._emit_debug("connection_flow.db_prompt_missing", connection=config.name)
                return

            def on_db_password(password: str | None) -> None:
                self._emit_debug(
                    "connection_flow.db_password",
                    connection=config.name,
                    provided=password is not None,
                    value_len=len(password) if password is not None else 0,
                )
                if password is None:
                    return
                temp_config = config.with_endpoint(password=password)
                self._emit_debug(
                    "connection_flow.ready",
                    connection=config.name,
                    db_type=str(config.db_type),
                    source="db_prompt",
                )
                on_ready(temp_config)

            self.prompter.prompt_db_password(config, on_db_password)
            return

        self._emit_debug("connection_flow.ready", connection=config.name, db_type=str(config.db_type))
        on_ready(config)
