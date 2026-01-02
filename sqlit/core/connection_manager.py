"""Core connection management utilities (UI-agnostic)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.shared.app.services import AppServices


@dataclass
class ConnectionTestResult:
    """Result of a connection test."""

    ok: bool
    error: Exception | None
    elapsed_seconds: float


class ConnectionManager:
    """Core connection operations independent of the UI."""

    def __init__(self, services: AppServices):
        self._services = services

    def populate_credentials(self, config: ConnectionConfig) -> ConnectionConfig:
        """Populate missing credentials from the credentials service."""
        endpoint = config.tcp_endpoint
        if endpoint and endpoint.password is not None and (not config.tunnel or config.tunnel.password is not None):
            return config

        service = self._services.credentials_service
        if endpoint and endpoint.password is None:
            password = service.get_password(config.name)
            if password is not None:
                endpoint.password = password
        if config.tunnel and config.tunnel.password is None:
            ssh_password = service.get_ssh_password(config.name)
            if ssh_password is not None:
                config.tunnel.password = ssh_password
        return config

    def connect(self, config: ConnectionConfig) -> Any:
        """Create a session for the given config."""
        return self._services.session_factory(config)

    def test_connection(self, config: ConnectionConfig) -> ConnectionTestResult:
        """Test a connection without mutating UI state."""
        import time

        start = time.perf_counter()
        tunnel = None
        error: Exception | None = None

        try:
            tunnel, host, port = self._services.tunnel_factory(config)
            if tunnel:
                connect_config = config.with_endpoint(host=host, port=str(port))
            else:
                connect_config = config

            provider = self._services.provider_factory(config.db_type)
            conn = provider.connection_factory.connect(connect_config)
            conn.close()
        except Exception as exc:
            error = exc
        finally:
            if tunnel:
                try:
                    tunnel.stop()
                except Exception:
                    pass

        elapsed = time.perf_counter() - start
        return ConnectionTestResult(ok=error is None, error=error, elapsed_seconds=elapsed)
