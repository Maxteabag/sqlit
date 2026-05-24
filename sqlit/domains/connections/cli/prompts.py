"""CLI prompts for connection credentials."""

from __future__ import annotations

import getpass
import sys

from sqlit.domains.connections.domain.config import ConnectionConfig
from sqlit.domains.connections.domain.password_command import (
    PasswordCommandError,
    run_password_command,
)


def _needs_ssh_prompt(config: ConnectionConfig) -> bool:
    """Check if SSH password is still missing (ignoring password_command)."""
    if not config.tunnel or not config.tunnel.enabled:
        return False
    if config.tunnel.auth_type != "password":
        return False
    return config.tunnel.password is None


def _needs_db_prompt(config: ConnectionConfig) -> bool:
    """Check if DB password is still missing (ignoring password_command)."""
    from sqlit.domains.connections.providers.metadata import is_file_based, requires_auth

    if is_file_based(config.db_type):
        return False
    if not requires_auth(config.db_type):
        return False
    auth_type = config.get_option("auth_type")
    if auth_type in ("ad_default", "ad_integrated", "windows"):
        return False
    endpoint = config.tcp_endpoint
    return bool(endpoint and endpoint.password is None)


def prompt_for_password(config: ConnectionConfig) -> ConnectionConfig:
    """Prompt for passwords if they are not set (None)."""
    new_config = config

    # SSH password
    if config.tunnel and config.tunnel.password is None:
        if config.tunnel.password_command:
            try:
                ssh_password = run_password_command(config.tunnel.password_command)
                new_config = new_config.with_tunnel(password=ssh_password)
            except PasswordCommandError as exc:
                print(f"Warning: SSH password command failed: {exc}", file=sys.stderr)
        if _needs_ssh_prompt(new_config):
            ssh_password = getpass.getpass(f"SSH password for '{config.name}': ")
            new_config = new_config.with_tunnel(password=ssh_password)

    # DB password
    endpoint = config.tcp_endpoint
    if endpoint and endpoint.password is None:
        if endpoint.password_command:
            try:
                db_password = run_password_command(endpoint.password_command)
                new_config = new_config.with_endpoint(password=db_password)
            except PasswordCommandError as exc:
                print(f"Warning: password command failed: {exc}", file=sys.stderr)
        if _needs_db_prompt(new_config):
            db_password = getpass.getpass(f"Password for '{config.name}': ")
            new_config = new_config.with_endpoint(password=db_password)

    return new_config
