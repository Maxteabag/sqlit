"""Integration tests for Firebird database operations."""

from __future__ import annotations

from .test_database_base import BaseDatabaseTests, DatabaseTestConfig


class TestFirebirdIntegration(BaseDatabaseTests):
    """Integration tests for Firebird database operations via CLI.

    These tests require a running Firebird instance (via Docker).
    Tests are skipped if Firebird is not available.
    """

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="firebird",
            display_name="Firebird",
            connection_fixture="firebird_connection",
            db_fixture="firebird_db",
            create_connection_args=lambda: [],  # Uses fixtures
        )

    def test_create_firebird_connection(self, firebird_db, cli_runner):
        """Test creating a Firebird connection via CLI."""
        from .conftest import (
            FIREBIRD_HOST,
            FIREBIRD_PASSWORD,
            FIREBIRD_PORT,
            FIREBIRD_USER,
        )

        connection_name = "test_create_firebird"

        try:
            # Create connection
            result = cli_runner(
                "connections",
                "add",
                "firebird",
                "--name",
                connection_name,
                "--server",
                FIREBIRD_HOST,
                "--port",
                str(FIREBIRD_PORT),
                "--database",
                firebird_db,
                "--username",
                FIREBIRD_USER,
                "--password",
                FIREBIRD_PASSWORD,
            )
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            # Verify it appears in list
            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "Firebird" in result.stdout

        finally:
            # Cleanup
            cli_runner("connection", "delete", connection_name, check=False)

    def test_delete_firebird_connection(self, firebird_db, cli_runner):
        """Test deleting a Firebird connection."""
        from .conftest import (
            FIREBIRD_HOST,
            FIREBIRD_PASSWORD,
            FIREBIRD_PORT,
            FIREBIRD_USER,
        )

        connection_name = "test_delete_firebird"

        # Create connection first
        cli_runner(
            "connections",
            "add",
            "firebird",
            "--name",
            connection_name,
            "--server",
            FIREBIRD_HOST,
            "--port",
            str(FIREBIRD_PORT),
            "--database",
            firebird_db,
            "--username",
            FIREBIRD_USER,
            "--password",
            FIREBIRD_PASSWORD,
        )

        # Delete it
        result = cli_runner("connection", "delete", connection_name)
        assert result.returncode == 0
        assert "deleted successfully" in result.stdout

        # Verify it's gone
        result = cli_runner("connection", "list")
        assert connection_name not in result.stdout
