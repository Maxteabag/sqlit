"""Integration tests for MariaDB database operations."""

from __future__ import annotations

from .test_database_base import BaseDatabaseTestsWithLimit, DatabaseTestConfig


class TestMariaDBIntegration(BaseDatabaseTestsWithLimit):
    """Integration tests for MariaDB database operations via CLI.

    These tests require a running MariaDB instance (via Docker).
    Tests are skipped if MariaDB is not available.
    """

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="mariadb",
            display_name="MariaDB",
            connection_fixture="mariadb_connection",
            db_fixture="mariadb_db",
            create_connection_args=lambda: [],  # Uses fixtures
        )

    def test_create_mariadb_connection(self, mariadb_db, cli_runner):
        """Test creating a MariaDB connection via CLI."""
        from .conftest import MARIADB_HOST, MARIADB_PASSWORD, MARIADB_PORT, MARIADB_USER

        connection_name = "test_create_mariadb"

        try:
            # Create connection
            result = cli_runner(
                "connection",
                "create",
                "--name",
                connection_name,
                "--db-type",
                "mariadb",
                "--server",
                MARIADB_HOST,
                "--port",
                str(MARIADB_PORT),
                "--database",
                mariadb_db,
                "--username",
                MARIADB_USER,
                "--password",
                MARIADB_PASSWORD,
            )
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            # Verify it appears in list
            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "MariaDB" in result.stdout

        finally:
            # Cleanup
            cli_runner("connection", "delete", connection_name, check=False)

    def test_delete_mariadb_connection(self, mariadb_db, cli_runner):
        """Test deleting a MariaDB connection."""
        from .conftest import MARIADB_HOST, MARIADB_PASSWORD, MARIADB_PORT, MARIADB_USER

        connection_name = "test_delete_mariadb"

        # Create connection first
        cli_runner(
            "connection",
            "create",
            "--name",
            connection_name,
            "--db-type",
            "mariadb",
            "--server",
            MARIADB_HOST,
            "--port",
            str(MARIADB_PORT),
            "--database",
            mariadb_db,
            "--username",
            MARIADB_USER,
            "--password",
            MARIADB_PASSWORD,
        )

        # Delete it
        result = cli_runner("connection", "delete", connection_name)
        assert result.returncode == 0
        assert "deleted successfully" in result.stdout

        # Verify it's gone
        result = cli_runner("connection", "list")
        assert connection_name not in result.stdout
