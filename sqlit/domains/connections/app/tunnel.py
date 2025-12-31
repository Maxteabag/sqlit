"""SSH tunnel support for database connections."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig


def ensure_ssh_tunnel_available() -> None:
    """Ensure SSH tunnel dependencies are installed."""
    try:
        import sshtunnel  # noqa: F401
    except Exception as e:
        from sqlit.domains.connections.providers.exceptions import MissingDriverError

        raise MissingDriverError(
            "SSH tunnel",
            "ssh",
            "sshtunnel",
            module_name="sshtunnel",
            import_error=str(e),
        ) from e


def create_ssh_tunnel(config: ConnectionConfig) -> tuple[Any, str, int]:
    """Create an SSH tunnel for the connection if SSH is enabled.

    Returns:
        Tuple of (tunnel_object, local_host, local_port) if SSH enabled,
        or (None, original_server, original_port) if SSH not enabled.
    """
    endpoint = config.tcp_endpoint
    if endpoint is None:
        return None, "", 0
    if not config.tunnel or not config.tunnel.enabled:
        port = int(endpoint.port) if endpoint.port else 0
        return None, endpoint.host, port

    ensure_ssh_tunnel_available()

    from sshtunnel import SSHTunnelForwarder

    # Parse remote database host and port
    remote_host = endpoint.host
    remote_port = int(endpoint.port) if endpoint.port else 0

    # SSH connection settings
    ssh_host = config.tunnel.host
    ssh_port = int(config.tunnel.port) if config.tunnel.port else 22
    ssh_username = config.tunnel.username

    # Build SSH auth kwargs
    ssh_kwargs: dict[str, Any] = {
        "ssh_username": ssh_username,
    }

    if config.tunnel.auth_type == "key":
        # Expand ~ in path
        key_path = os.path.expanduser(config.tunnel.key_path)
        if Path(key_path).exists():
            ssh_kwargs["ssh_pkey"] = key_path
        else:
            raise ValueError(f"SSH key file not found: {key_path}")
    else:
        ssh_kwargs["ssh_password"] = config.tunnel.password

    # Create tunnel
    tunnel = SSHTunnelForwarder(
        (ssh_host, ssh_port),
        remote_bind_address=(remote_host, remote_port),
        **ssh_kwargs,
    )
    tunnel.start()

    return tunnel, "127.0.0.1", tunnel.local_bind_port


def create_noop_tunnel(config: ConnectionConfig) -> tuple[Any, str, int]:
    """Return the original endpoint without creating a tunnel."""
    endpoint = config.tcp_endpoint
    if endpoint is None:
        return None, "", 0
    port = int(endpoint.port) if endpoint.port else 0
    return None, endpoint.host, port
