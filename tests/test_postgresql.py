"""Integration tests for PostgreSQL database operations."""

from __future__ import annotations

from .test_database_base import BaseDatabaseTestsWithLimit, DatabaseTestConfig


class TestPostgreSQLIntegration(BaseDatabaseTestsWithLimit):
    """Integration tests for PostgreSQL database operations via CLI.

    These tests require a running PostgreSQL instance (via Docker).
    Tests are skipped if PostgreSQL is not available.
    """

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="postgresql",
            display_name="PostgreSQL",
            connection_fixture="postgres_connection",
            db_fixture="postgres_db",
            create_connection_args=lambda: [],  # Uses fixtures
        )

    def test_create_postgres_connection(self, postgres_db, cli_runner):
        """Test creating a PostgreSQL connection via CLI."""
        from .conftest import (
            POSTGRES_HOST,
            POSTGRES_PASSWORD,
            POSTGRES_PORT,
            POSTGRES_USER,
        )

        connection_name = "test_create_postgres"

        try:
            # Create connection
            result = cli_runner(
                "connection",
                "create",
                "--name",
                connection_name,
                "--db-type",
                "postgresql",
                "--server",
                POSTGRES_HOST,
                "--port",
                str(POSTGRES_PORT),
                "--database",
                postgres_db,
                "--username",
                POSTGRES_USER,
                "--password",
                POSTGRES_PASSWORD,
            )
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            # Verify it appears in list
            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "PostgreSQL" in result.stdout

        finally:
            # Cleanup
            cli_runner("connection", "delete", connection_name, check=False)

    def test_delete_postgres_connection(self, postgres_db, cli_runner):
        """Test deleting a PostgreSQL connection."""
        from .conftest import (
            POSTGRES_HOST,
            POSTGRES_PASSWORD,
            POSTGRES_PORT,
            POSTGRES_USER,
        )

        connection_name = "test_delete_postgres"

        # Create connection first
        cli_runner(
            "connection",
            "create",
            "--name",
            connection_name,
            "--db-type",
            "postgresql",
            "--server",
            POSTGRES_HOST,
            "--port",
            str(POSTGRES_PORT),
            "--database",
            postgres_db,
            "--username",
            POSTGRES_USER,
            "--password",
            POSTGRES_PASSWORD,
        )

        # Delete it
        result = cli_runner("connection", "delete", connection_name)
        assert result.returncode == 0
        assert "deleted successfully" in result.stdout

        # Verify it's gone
        result = cli_runner("connection", "list")
        assert connection_name not in result.stdout
