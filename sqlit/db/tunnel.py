"""SSH tunnel support for database connections."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..config import ConnectionConfig


def ensure_ssh_tunnel_available() -> None:
    """Ensure SSH tunnel dependencies are installed."""
    forced_missing = os.environ.get("SQLIT_MOCK_MISSING_DRIVERS", "").strip()
    if forced_missing:
        forced = {s.strip() for s in forced_missing.split(",") if s.strip()}
        if "ssh" in forced:
            from .exceptions import MissingDriverError

            raise MissingDriverError("SSH tunnel", "ssh", "sshtunnel")
    try:
        import sshtunnel  # noqa: F401
    except Exception as e:
        from .exceptions import MissingDriverError

        raise MissingDriverError("SSH tunnel", "ssh", "sshtunnel") from e


def create_ssh_tunnel(config: ConnectionConfig) -> tuple[Any, str, int]:
    """Create an SSH tunnel for the connection if SSH is enabled.

    Returns:
        Tuple of (tunnel_object, local_host, local_port) if SSH enabled,
        or (None, original_server, original_port) if SSH not enabled.
    """
    if not config.ssh_enabled:
        port = int(config.port) if config.port else 0
        return None, config.server, port

    ensure_ssh_tunnel_available()

    from sshtunnel import SSHTunnelForwarder

    # Parse remote database host and port
    remote_host = config.server
    remote_port = int(config.port) if config.port else 0

    # SSH connection settings
    ssh_host = config.ssh_host
    ssh_port = int(config.ssh_port) if config.ssh_port else 22
    ssh_username = config.ssh_username

    # Build SSH auth kwargs
    ssh_kwargs: dict[str, Any] = {
        "ssh_username": ssh_username,
    }

    if config.ssh_auth_type == "key":
        # Expand ~ in path
        key_path = os.path.expanduser(config.ssh_key_path)
        if Path(key_path).exists():
            ssh_kwargs["ssh_pkey"] = key_path
        else:
            raise ValueError(f"SSH key file not found: {key_path}")
    else:
        ssh_kwargs["ssh_password"] = config.ssh_password

    # Create tunnel
    tunnel = SSHTunnelForwarder(
        (ssh_host, ssh_port),
        remote_bind_address=(remote_host, remote_port),
        **ssh_kwargs,
    )
    tunnel.start()

    return tunnel, "127.0.0.1", tunnel.local_bind_port
