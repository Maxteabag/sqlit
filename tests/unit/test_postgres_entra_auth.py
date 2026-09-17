"""PostgreSQL Azure Entra authentication configuration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sqlit.domains.connections.domain.passwords import needs_db_password
from sqlit.domains.connections.providers.postgresql import adapter as adapter_module
from sqlit.domains.connections.providers.postgresql.adapter import PostgreSQLAdapter
from sqlit.domains.connections.providers.postgresql.auth import (
    AZURE_ENTRA_PASSWORD_COMMAND,
    POSTGRES_AUTH_AZURE_ENTRA_CLI,
    POSTGRES_AUTH_PASSWORD,
    normalize_postgres_auth,
)
from sqlit.domains.connections.providers.postgresql.schema import SCHEMA
from tests.helpers import ConnectionConfig


def test_entra_auth_adds_dynamic_azure_cli_token_command() -> None:
    config = ConnectionConfig(
        name="azure-postgres",
        db_type="postgresql",
        server="example.postgres.database.azure.com",
        username="developer@example.com",
        password="must-not-be-stored",
        options={"postgres_auth_method": POSTGRES_AUTH_AZURE_ENTRA_CLI},
    )

    normalized = PostgreSQLAdapter().normalize_config(config)

    assert normalized.tcp_endpoint is not None
    assert normalized.tcp_endpoint.password is None
    assert normalized.tcp_endpoint.password_command == AZURE_ENTRA_PASSWORD_COMMAND
    assert needs_db_password(normalized) is False


def test_switching_back_to_password_removes_managed_command() -> None:
    config = ConnectionConfig(
        name="azure-postgres",
        db_type="postgresql",
        options={"postgres_auth_method": POSTGRES_AUTH_PASSWORD},
        password_command=AZURE_ENTRA_PASSWORD_COMMAND,
    )

    normalized = PostgreSQLAdapter().normalize_config(config)

    assert normalized.tcp_endpoint is not None
    assert normalized.tcp_endpoint.password_command is None


def test_existing_azure_password_command_migrates_to_entra_auth() -> None:
    config = ConnectionConfig(
        name="legacy-azure-postgres",
        db_type="postgresql",
        password_command=AZURE_ENTRA_PASSWORD_COMMAND,
    )

    normalized = normalize_postgres_auth(config)

    assert normalized.get_option("postgres_auth_method") == POSTGRES_AUTH_AZURE_ENTRA_CLI
    assert normalized.tcp_endpoint is not None
    assert normalized.tcp_endpoint.password_command == AZURE_ENTRA_PASSWORD_COMMAND


def test_normalization_clears_stale_password_in_entra_mode() -> None:
    config = ConnectionConfig(
        name="azure-postgres",
        db_type="postgresql",
        options={"postgres_auth_method": POSTGRES_AUTH_AZURE_ENTRA_CLI},
    )
    adapter = PostgreSQLAdapter()
    first = adapter.normalize_config(config)
    assert first.tcp_endpoint is not None
    first.tcp_endpoint.password = "fresh-access-token"

    second = adapter.normalize_config(first)

    assert second.tcp_endpoint is not None
    assert second.tcp_endpoint.password is None
    assert second.tcp_endpoint.password_command == AZURE_ENTRA_PASSWORD_COMMAND


def test_password_field_only_visible_for_password_auth() -> None:
    password_field = next(field for field in SCHEMA.fields if field.name == "password")
    assert password_field.visible_when is not None
    assert password_field.visible_when({"postgres_auth_method": POSTGRES_AUTH_PASSWORD})
    assert not password_field.visible_when({"postgres_auth_method": POSTGRES_AUTH_AZURE_ENTRA_CLI})


def test_adapter_resolves_entra_token_for_direct_connection_paths() -> None:
    config = ConnectionConfig(
        name="azure-postgres",
        db_type="postgresql",
        server="example.postgres.database.azure.com",
        database="appdb",
        username="developer@example.com",
        options={"postgres_auth_method": POSTGRES_AUTH_AZURE_ENTRA_CLI},
    )
    adapter = PostgreSQLAdapter()
    driver = MagicMock()
    connection = MagicMock()
    driver.connect.return_value = connection
    adapter._import_driver_module = MagicMock(return_value=driver)  # type: ignore[method-assign]

    with (
        patch(
            "sqlit.domains.connections.domain.password_command.run_password_command",
            return_value="fresh-token",
        ) as run_command,
        patch.object(adapter_module, "_register_temporal_typecasters"),
    ):
        result = adapter.connect(config)

    assert result is connection
    run_command.assert_called_once_with(AZURE_ENTRA_PASSWORD_COMMAND)
    driver.connect.assert_called_once()
    assert driver.connect.call_args.kwargs["password"] == "fresh-token"
