"""Dynamic password-command coverage for TUI connection management."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sqlit.core.connection_manager import ConnectionManager
from sqlit.domains.connections.domain.password_command import PasswordCommandError
from sqlit.domains.connections.providers.postgresql.auth import (
    AZURE_ENTRA_PASSWORD_COMMAND,
    POSTGRES_AUTH_AZURE_ENTRA_CLI,
)
from tests.helpers import ConnectionConfig


def test_connect_keeps_postgres_dynamic_command_unresolved_in_session() -> None:
    captured_configs: list[ConnectionConfig] = []
    services = MagicMock()
    services.session_factory.side_effect = captured_configs.append
    manager = ConnectionManager(services)
    config = ConnectionConfig(
        name="azure-postgres",
        db_type="postgresql",
        server="example.postgres.database.azure.com",
        username="developer@example.com",
        password=None,
        options={"postgres_auth_method": POSTGRES_AUTH_AZURE_ENTRA_CLI},
    )

    with patch(
        "sqlit.domains.connections.domain.password_command.run_password_command",
    ) as run_command:
        manager.connect(config)
        manager.connect(config)

    run_command.assert_not_called()
    assert len(captured_configs) == 2
    for captured in captured_configs:
        assert captured.tcp_endpoint is not None
        assert captured.tcp_endpoint.password is None
        assert captured.tcp_endpoint.password_command == AZURE_ENTRA_PASSWORD_COMMAND
    assert config.tcp_endpoint is not None
    assert config.tcp_endpoint.password is None


def test_connection_test_resolves_dynamic_password_in_postgres_adapter() -> None:
    from sqlit.domains.connections.providers.postgresql.adapter import PostgreSQLAdapter

    connection = MagicMock()
    driver = MagicMock()
    driver.connect.return_value = connection
    adapter = PostgreSQLAdapter()
    adapter._import_driver_module = MagicMock(return_value=driver)  # type: ignore[method-assign]
    provider = MagicMock()
    provider.connection_factory = adapter
    services = MagicMock()
    services.tunnel_factory.return_value = (None, "localhost", 5432)
    services.provider_factory.return_value = provider
    manager = ConnectionManager(services)
    config = ConnectionConfig(
        name="azure-postgres",
        db_type="postgresql",
        options={"postgres_auth_method": POSTGRES_AUTH_AZURE_ENTRA_CLI},
    )

    with (
        patch(
            "sqlit.domains.connections.domain.password_command.run_password_command",
            return_value="fresh-token",
        ),
        patch("sqlit.domains.connections.providers.postgresql.adapter._register_temporal_typecasters"),
    ):
        result = manager.test_connection(config)

    assert result.ok is True
    assert driver.connect.call_args.kwargs["password"] == "fresh-token"
    connection.close.assert_called_once()


def test_connection_test_surfaces_password_command_failure() -> None:
    from sqlit.domains.connections.providers.postgresql.adapter import PostgreSQLAdapter

    services = MagicMock()
    adapter = PostgreSQLAdapter()
    adapter._import_driver_module = MagicMock(return_value=MagicMock())  # type: ignore[method-assign]
    provider = MagicMock()
    provider.connection_factory = adapter
    services.tunnel_factory.return_value = (None, "localhost", 5432)
    services.provider_factory.return_value = provider
    manager = ConnectionManager(services)
    config = ConnectionConfig(
        name="azure-postgres",
        db_type="postgresql",
        options={"postgres_auth_method": POSTGRES_AUTH_AZURE_ENTRA_CLI},
    )

    with patch(
        "sqlit.domains.connections.domain.password_command.run_password_command",
        side_effect=PasswordCommandError("Azure CLI login required"),
    ):
        result = manager.test_connection(config)

    assert result.ok is False
    assert isinstance(result.error, PasswordCommandError)
    assert "Azure CLI login required" in str(result.error)


def test_connect_does_not_run_ssh_password_command_for_key_auth() -> None:
    services = MagicMock()
    manager = ConnectionManager(services)
    config = ConnectionConfig(
        name="postgres-through-bastion",
        db_type="postgresql",
        password="database-password",
        ssh_enabled=True,
        ssh_host="bastion",
        ssh_username="developer",
        ssh_auth_type="key",
        ssh_key_path="~/.ssh/id_ed25519",
        ssh_password_command="must-not-run",
    )

    with patch("sqlit.domains.connections.domain.password_command.run_password_command") as run_command:
        manager.connect(config)

    run_command.assert_not_called()
    services.session_factory.assert_called_once()


def test_connect_prefers_explicit_passwords_over_commands() -> None:
    services = MagicMock()
    manager = ConnectionManager(services)
    config = ConnectionConfig(
        name="explicit-passwords",
        db_type="mysql",
        server="localhost",
        username="developer",
        password="database-password",
        password_command="must-not-run-db",
        ssh_enabled=True,
        ssh_host="bastion",
        ssh_username="developer",
        ssh_auth_type="password",
        ssh_password="ssh-password",
        ssh_password_command="must-not-run-ssh",
    )

    with patch("sqlit.domains.connections.domain.password_command.run_password_command") as run_command:
        manager.connect(config)

    run_command.assert_not_called()


def test_populate_credentials_does_not_override_ssh_password_command() -> None:
    services = MagicMock()
    services.credentials_service.get_ssh_password.return_value = "stale-password"
    manager = ConnectionManager(services)
    config = ConnectionConfig(
        name="ssh-command",
        db_type="postgresql",
        password="database-password",
        ssh_enabled=True,
        ssh_host="bastion",
        ssh_username="developer",
        ssh_auth_type="password",
        ssh_password_command="dynamic-ssh-password",
    )

    manager.populate_credentials(config)

    assert config.tunnel is not None
    assert config.tunnel.password is None
    services.credentials_service.get_ssh_password.assert_not_called()
