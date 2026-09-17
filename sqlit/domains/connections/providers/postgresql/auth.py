"""Authentication helpers for PostgreSQL connections."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig

POSTGRES_AUTH_PASSWORD = "password"
POSTGRES_AUTH_AZURE_ENTRA_CLI = "azure_entra_cli"
AZURE_ENTRA_PASSWORD_COMMAND = "az account get-access-token --resource-type oss-rdbms --query accessToken --output tsv"


def get_postgres_auth_method(config: ConnectionConfig) -> str:
    return str(config.get_option("postgres_auth_method", POSTGRES_AUTH_PASSWORD)).lower()


def normalize_postgres_auth(config: ConnectionConfig) -> ConnectionConfig:
    endpoint = config.tcp_endpoint
    if endpoint is None:
        return config
    if "postgres_auth_method" not in config.options and endpoint.password_command == AZURE_ENTRA_PASSWORD_COMMAND:
        # Preserve and adopt connections that used the generic password-command
        # support before Azure Entra became a first-class authentication mode.
        config.set_option("postgres_auth_method", POSTGRES_AUTH_AZURE_ENTRA_CLI)
    if get_postgres_auth_method(config) == POSTGRES_AUTH_AZURE_ENTRA_CLI:
        endpoint.password = None
        endpoint.password_command = AZURE_ENTRA_PASSWORD_COMMAND
    elif endpoint.password_command == AZURE_ENTRA_PASSWORD_COMMAND:
        endpoint.password_command = None
    return config
