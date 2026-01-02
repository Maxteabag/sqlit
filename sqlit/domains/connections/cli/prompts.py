"""CLI prompts for connection credentials."""

from __future__ import annotations

import getpass

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.domain.passwords import needs_db_password, needs_ssh_password


def prompt_for_password(config: ConnectionConfig) -> ConnectionConfig:
    """Prompt for passwords if they are not set (None)."""
    new_config = config

    if needs_ssh_password(config):
        ssh_password = getpass.getpass(f"SSH password for '{config.name}': ")
        new_config = new_config.with_tunnel(password=ssh_password)

    if needs_db_password(config):
        db_password = getpass.getpass(f"Password for '{config.name}': ")
        new_config = new_config.with_endpoint(password=db_password)

    return new_config
