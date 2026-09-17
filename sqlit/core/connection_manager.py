"""Core connection management utilities (UI-agnostic)."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.domain.passwords import uses_db_password
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
        if endpoint and endpoint.password is None and not endpoint.password_command and uses_db_password(config):
            password = service.get_password(config.name)
            if password is not None:
                endpoint.password = password
        if config.tunnel and config.tunnel.password is None and not config.tunnel.password_command:
            ssh_password = service.get_ssh_password(config.name)
            if ssh_password is not None:
                config.tunnel.password = ssh_password
        return config

    def _resolve_dynamic_credentials(self, config: ConnectionConfig) -> ConnectionConfig:
        """Resolve commands on a copy so short-lived secrets are not persisted."""
        from sqlit.domains.connections.domain.password_command import (
            run_password_command,
        )
        from sqlit.domains.connections.providers.config_service import (
            normalize_connection_config,
        )

        resolved = normalize_connection_config(copy.deepcopy(config))
        endpoint = resolved.tcp_endpoint
        if endpoint and endpoint.password is None and endpoint.password_command and resolved.db_type != "postgresql":
            # PostgreSQL resolves this at the adapter boundary so reconnects and
            # database switches always fetch a fresh short-lived token.
            endpoint.password = run_password_command(endpoint.password_command)
        if resolved.tunnel and resolved.tunnel.auth_type == "password" and resolved.tunnel.password is None and resolved.tunnel.password_command:
            resolved.tunnel.password = run_password_command(resolved.tunnel.password_command)
        return resolved

    def connect(self, config: ConnectionConfig) -> Any:
        """Create a session for the given config."""
        return self._services.session_factory(self._resolve_dynamic_credentials(config))

    def test_connection(self, config: ConnectionConfig) -> ConnectionTestResult:
        """Test a connection without mutating UI state."""
        import time

        start = time.perf_counter()
        tunnel = None
        error: Exception | None = None

        try:
            resolved = self._resolve_dynamic_credentials(config)
            tunnel, host, port = self._services.tunnel_factory(resolved)
            if tunnel:
                connect_config = resolved.with_endpoint(host=host, port=str(port))
            else:
                connect_config = resolved

            provider = self._services.provider_factory(resolved.db_type)
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
