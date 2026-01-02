"""Password prompt rules for connection configs."""

from __future__ import annotations

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.providers.metadata import is_file_based


def needs_db_password(config: ConnectionConfig) -> bool:
    """Return True if the database password should be prompted."""
    if is_file_based(config.db_type):
        return False

    auth_type = config.get_option("auth_type")
    if auth_type in ("ad_default", "ad_integrated", "windows"):
        return False

    endpoint = config.tcp_endpoint
    return bool(endpoint and endpoint.password is None)


def needs_ssh_password(config: ConnectionConfig) -> bool:
    """Return True if the SSH password should be prompted."""
    if not config.tunnel or not config.tunnel.enabled:
        return False

    if config.tunnel.auth_type != "password":
        return False

    return config.tunnel.password is None
