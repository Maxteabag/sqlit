"""Helpers for safely persisting connections without dropping stored passwords."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlit.domains.connections.app.credentials import CredentialsService
    from sqlit.domains.connections.domain.config import ConnectionConfig


def build_persist_connections(
    connections: list[ConnectionConfig],
    credentials_service: CredentialsService,
) -> list[ConnectionConfig]:
    """Return a copy of connections with missing passwords filled from storage.

    This prevents saves from clearing stored passwords when the in-memory
    connection list was loaded without credentials.
    """
    persist_connections = copy.deepcopy(connections)
    for conn in persist_connections:
        endpoint = conn.tcp_endpoint
        if endpoint and endpoint.password is None:
            stored = credentials_service.get_password(conn.name)
            if stored is not None:
                endpoint.password = stored

        if conn.tunnel and conn.tunnel.password is None:
            stored_ssh = credentials_service.get_ssh_password(conn.name)
            if stored_ssh is not None:
                conn.tunnel.password = stored_ssh

    return persist_connections
