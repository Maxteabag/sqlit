"""Tests for connection flow password_command integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sqlit.domains.connections.app.connection_flow import ConnectionFlow
from tests.helpers import ConnectionConfig


class TestPopulateCredentialsPasswordCommand:
    def _make_flow(self, *, keyring_password: str | None = None) -> ConnectionFlow:
        services = MagicMock()
        services.credentials_service.get_password.return_value = keyring_password
        services.credentials_service.get_ssh_password.return_value = None
        return ConnectionFlow(services=services)

    @patch("sqlit.domains.connections.app.connection_flow.run_password_command", return_value="cmd_pw")
    def test_runs_password_command_when_keyring_empty(self, mock_run: MagicMock) -> None:
        flow = self._make_flow(keyring_password=None)
        config = ConnectionConfig(
            name="test",
            db_type="postgresql",
            server="localhost",
            username="user",
            password=None,
            password_command="echo cmd_pw",
        )
        flow.populate_credentials_if_missing(config)
        mock_run.assert_called_once_with("echo cmd_pw")
        assert config.tcp_endpoint is not None
        assert config.tcp_endpoint.password == "cmd_pw"

    @patch("sqlit.domains.connections.app.connection_flow.run_password_command")
    def test_keyring_password_wins_over_command(self, mock_run: MagicMock) -> None:
        flow = self._make_flow(keyring_password="keyring_pw")
        config = ConnectionConfig(
            name="test",
            db_type="postgresql",
            server="localhost",
            username="user",
            password=None,
            password_command="echo cmd_pw",
        )
        flow.populate_credentials_if_missing(config)
        mock_run.assert_not_called()
        assert config.tcp_endpoint is not None
        assert config.tcp_endpoint.password == "keyring_pw"
