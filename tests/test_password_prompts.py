"""Tests for password prompt functionality."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest

from sqlit.commands import _prompt_for_password
from sqlit.config import ConnectionConfig
from sqlit.ui.mixins.connection import _needs_db_password, _needs_ssh_password


class TestNeedsDbPassword:
    """Test _needs_db_password helper function."""

    def test_file_based_database_does_not_need_password(self) -> None:
        """SQLite and DuckDB don't need passwords."""
        sqlite_config = ConnectionConfig(
            name="test",
            db_type="sqlite",
            file_path="/tmp/test.db",
            password="",
        )
        assert not _needs_db_password(sqlite_config)

        duckdb_config = ConnectionConfig(
            name="test",
            db_type="duckdb",
            file_path="/tmp/test.duckdb",
            password="",
        )
        assert not _needs_db_password(duckdb_config)

    def test_server_database_with_none_password_needs_prompt(self) -> None:
        """PostgreSQL/MySQL with None password (not set) needs prompt."""
        postgres_config = ConnectionConfig(
            name="test",
            db_type="postgresql",
            server="localhost",
            username="user",
            password=None,
        )
        assert _needs_db_password(postgres_config)

        mysql_config = ConnectionConfig(
            name="test",
            db_type="mysql",
            server="localhost",
            username="user",
            password=None,
        )
        assert _needs_db_password(mysql_config)

    def test_server_database_with_empty_password_no_prompt(self) -> None:
        """PostgreSQL/MySQL with empty string password (explicitly empty) doesn't need prompt."""
        postgres_config = ConnectionConfig(
            name="test",
            db_type="postgresql",
            server="localhost",
            username="user",
            password="",  # Explicitly empty, valid for some DBs
        )
        assert not _needs_db_password(postgres_config)

        mysql_config = ConnectionConfig(
            name="test",
            db_type="mysql",
            server="localhost",
            username="user",
            password="",
        )
        assert not _needs_db_password(mysql_config)

    def test_server_database_with_stored_password_does_not_need_prompt(self) -> None:
        """Database with stored password doesn't need prompt."""
        config = ConnectionConfig(
            name="test",
            db_type="postgresql",
            server="localhost",
            username="user",
            password="stored_password",
        )
        assert not _needs_db_password(config)

    def test_mssql_with_none_password_needs_prompt(self) -> None:
        """SQL Server with SQL auth and None password needs prompt."""
        config = ConnectionConfig(
            name="test",
            db_type="mssql",
            server="localhost",
            username="sa",
            password=None,
            auth_type="sql",
        )
        assert _needs_db_password(config)

    def test_mssql_windows_auth_with_none_password(self) -> None:
        """SQL Server with Windows auth and None password still technically needs prompt.

        Note: In practice Windows auth doesn't use the password field,
        but the function returns True because password is None.
        """
        config = ConnectionConfig(
            name="test",
            db_type="mssql",
            server="localhost",
            password=None,
            auth_type="windows",
            trusted_connection=True,
        )
        assert _needs_db_password(config)

    def test_mssql_windows_auth_with_empty_password_no_prompt(self) -> None:
        """SQL Server with Windows auth and empty string password doesn't need prompt."""
        config = ConnectionConfig(
            name="test",
            db_type="mssql",
            server="localhost",
            password="",  # Explicitly empty
            auth_type="windows",
            trusted_connection=True,
        )
        assert not _needs_db_password(config)


class TestNeedsSshPassword:
    """Test _needs_ssh_password helper function."""

    def test_ssh_disabled_does_not_need_password(self) -> None:
        """Config without SSH doesn't need SSH password."""
        config = ConnectionConfig(
            name="test",
            db_type="postgresql",
            server="localhost",
            ssh_enabled=False,
        )
        assert not _needs_ssh_password(config)

    def test_ssh_key_auth_does_not_need_password(self) -> None:
        """SSH with key auth doesn't need password."""
        config = ConnectionConfig(
            name="test",
            db_type="postgresql",
            server="localhost",
            ssh_enabled=True,
            ssh_auth_type="key",
            ssh_key_path="~/.ssh/id_rsa",
            ssh_password="",
        )
        assert not _needs_ssh_password(config)

    def test_ssh_password_auth_with_none_password_needs_prompt(self) -> None:
        """SSH with password auth and None password (not set) needs prompt."""
        config = ConnectionConfig(
            name="test",
            db_type="postgresql",
            server="localhost",
            ssh_enabled=True,
            ssh_auth_type="password",
            ssh_host="bastion.example.com",
            ssh_username="user",
            ssh_password=None,
        )
        assert _needs_ssh_password(config)

    def test_ssh_password_auth_with_empty_password_no_prompt(self) -> None:
        """SSH with password auth and empty string password (explicitly empty) no prompt."""
        config = ConnectionConfig(
            name="test",
            db_type="postgresql",
            server="localhost",
            ssh_enabled=True,
            ssh_auth_type="password",
            ssh_host="bastion.example.com",
            ssh_username="user",
            ssh_password="",  # Explicitly empty
        )
        assert not _needs_ssh_password(config)

    def test_ssh_password_auth_with_stored_password_does_not_need_prompt(self) -> None:
        """SSH with stored password doesn't need prompt."""
        config = ConnectionConfig(
            name="test",
            db_type="postgresql",
            server="localhost",
            ssh_enabled=True,
            ssh_auth_type="password",
            ssh_host="bastion.example.com",
            ssh_username="user",
            ssh_password="stored_password",
        )
        assert not _needs_ssh_password(config)


class TestCliPromptForPassword:
    """Test CLI _prompt_for_password function."""

    def test_file_based_no_prompt(self) -> None:
        """File-based databases don't trigger password prompt."""
        config = ConnectionConfig(
            name="test",
            db_type="sqlite",
            file_path="/tmp/test.db",
        )

        with patch("sqlit.commands.getpass.getpass") as mock_getpass:
            result = _prompt_for_password(config)
            mock_getpass.assert_not_called()
            assert result == config

    @patch("sqlit.commands.getpass.getpass", return_value="test_password")
    def test_database_password_prompt(self, mock_getpass: MagicMock) -> None:
        """None database password triggers getpass prompt."""
        config = ConnectionConfig(
            name="mydb",
            db_type="postgresql",
            server="localhost",
            username="user",
            password=None,
        )

        result = _prompt_for_password(config)

        mock_getpass.assert_called_once_with("Password for 'mydb': ")
        assert result.password == "test_password"
        assert result.name == "mydb"
        assert result.server == "localhost"

    @patch("sqlit.commands.getpass.getpass")
    def test_empty_password_no_prompt(self, mock_getpass: MagicMock) -> None:
        """Empty string password (explicitly set) does not trigger prompt."""
        config = ConnectionConfig(
            name="mydb",
            db_type="postgresql",
            server="localhost",
            username="user",
            password="",  # Explicitly empty
        )

        result = _prompt_for_password(config)

        mock_getpass.assert_not_called()
        assert result == config
        assert result.password == ""

    @patch("sqlit.commands.getpass.getpass")
    def test_stored_password_no_prompt(self, mock_getpass: MagicMock) -> None:
        """Stored database password doesn't trigger prompt."""
        config = ConnectionConfig(
            name="mydb",
            db_type="postgresql",
            server="localhost",
            username="user",
            password="stored_password",
        )

        result = _prompt_for_password(config)

        mock_getpass.assert_not_called()
        assert result == config
        assert result.password == "stored_password"

    @patch("sqlit.commands.getpass.getpass")
    def test_ssh_password_prompt(self, mock_getpass: MagicMock) -> None:
        """None SSH password triggers getpass prompt."""
        mock_getpass.side_effect = ["ssh_pass", "db_pass"]

        config = ConnectionConfig(
            name="mydb",
            db_type="postgresql",
            server="localhost",
            username="user",
            password=None,
            ssh_enabled=True,
            ssh_auth_type="password",
            ssh_host="bastion.example.com",
            ssh_username="sshuser",
            ssh_password=None,
        )

        result = _prompt_for_password(config)

        assert mock_getpass.call_count == 2
        mock_getpass.assert_any_call("SSH password for 'mydb': ")
        mock_getpass.assert_any_call("Password for 'mydb': ")
        assert result.ssh_password == "ssh_pass"
        assert result.password == "db_pass"

    @patch("sqlit.commands.getpass.getpass", return_value="ssh_pass")
    def test_ssh_password_only(self, mock_getpass: MagicMock) -> None:
        """SSH password prompt without database password."""
        config = ConnectionConfig(
            name="mydb",
            db_type="postgresql",
            server="localhost",
            username="user",
            password="stored_db_password",
            ssh_enabled=True,
            ssh_auth_type="password",
            ssh_host="bastion.example.com",
            ssh_username="sshuser",
            ssh_password=None,
        )

        result = _prompt_for_password(config)

        mock_getpass.assert_called_once_with("SSH password for 'mydb': ")
        assert result.ssh_password == "ssh_pass"
        assert result.password == "stored_db_password"

    @patch("sqlit.commands.getpass.getpass", return_value="")
    def test_user_enters_empty_password(self, mock_getpass: MagicMock) -> None:
        """User can enter empty password (just press Enter) when prompted."""
        config = ConnectionConfig(
            name="mydb",
            db_type="postgresql",
            server="localhost",
            username="user",
            password=None,  # None triggers prompt
        )

        result = _prompt_for_password(config)

        mock_getpass.assert_called_once()
        assert result.password == ""

    def test_original_config_not_modified(self) -> None:
        """Original config object is not modified."""
        original = ConnectionConfig(
            name="mydb",
            db_type="postgresql",
            server="localhost",
            username="user",
            password=None,
        )

        with patch("sqlit.commands.getpass.getpass", return_value="new_password"):
            result = _prompt_for_password(original)

        # Original should still have None password
        assert original.password is None
        # Result should have the new password
        assert result.password == "new_password"
        # They should be different objects
        assert result is not original


class TestPasswordPromptIntegration:
    """Integration tests for the full password prompt flow."""

    @patch("sqlit.commands.getpass.getpass", return_value="test123")
    def test_cli_query_with_none_password(self, mock_getpass: MagicMock) -> None:
        """CLI query command prompts for password when config has None password."""
        from sqlit.commands import cmd_query
        from sqlit.config import save_connections

        # Create a test connection with None password (not set)
        config = ConnectionConfig(
            name="test_connection",
            db_type="postgresql",
            server="localhost",
            port="5432",
            database="testdb",
            username="testuser",
            password=None,  # None = not set, will prompt
        )

        # Save it
        save_connections([config])

        # Mock arguments
        args = MagicMock()
        args.connection = "test_connection"
        args.database = None
        args.query = "SELECT 1"
        args.file = None
        args.format = "table"
        args.limit = 1000

        # Mock the session factory to avoid actual connection
        def mock_session_factory(config):
            raise Exception("Connection test - should have prompted for password")

        # This will fail at connection but should have prompted for password
        try:
            cmd_query(args, session_factory=mock_session_factory)
        except Exception:
            pass

        # Verify getpass was called
        mock_getpass.assert_called_once_with("Password for 'test_connection': ")

    def test_config_with_both_passwords_none(self) -> None:
        """Config with both DB and SSH passwords None needs both prompts."""
        config = ConnectionConfig(
            name="mydb",
            db_type="postgresql",
            server="localhost",
            username="user",
            password=None,
            ssh_enabled=True,
            ssh_auth_type="password",
            ssh_host="bastion.example.com",
            ssh_username="sshuser",
            ssh_password=None,
        )

        assert _needs_db_password(config)
        assert _needs_ssh_password(config)

        with patch("sqlit.commands.getpass.getpass") as mock_getpass:
            mock_getpass.side_effect = ["ssh_password", "db_password"]
            result = _prompt_for_password(config)

            assert result.ssh_password == "ssh_password"
            assert result.password == "db_password"
            assert mock_getpass.call_count == 2

    def test_config_with_both_passwords_empty_no_prompt(self) -> None:
        """Config with both DB and SSH passwords empty (explicit) doesn't need prompts."""
        config = ConnectionConfig(
            name="mydb",
            db_type="postgresql",
            server="localhost",
            username="user",
            password="",  # Explicitly empty
            ssh_enabled=True,
            ssh_auth_type="password",
            ssh_host="bastion.example.com",
            ssh_username="sshuser",
            ssh_password="",  # Explicitly empty
        )

        assert not _needs_db_password(config)
        assert not _needs_ssh_password(config)

        with patch("sqlit.commands.getpass.getpass") as mock_getpass:
            result = _prompt_for_password(config)

            mock_getpass.assert_not_called()
            assert result.password == ""
            assert result.ssh_password == ""
