"""Integration tests for MySQL database operations."""

from __future__ import annotations

from .test_database_base import BaseDatabaseTestsWithLimit, DatabaseTestConfig


class TestMySQLIntegration(BaseDatabaseTestsWithLimit):
    """Integration tests for MySQL database operations via CLI.

    These tests require a running MySQL instance (via Docker).
    Tests are skipped if MySQL is not available.
    """

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="mysql",
            display_name="MySQL",
            connection_fixture="mysql_connection",
            db_fixture="mysql_db",
            create_connection_args=lambda: [],  # Uses fixtures
        )

    def test_create_mysql_connection(self, mysql_db, cli_runner):
        """Test creating a MySQL connection via CLI."""
        from .conftest import MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER

        connection_name = "test_create_mysql"

        try:
            # Create connection
            result = cli_runner(
                "connections",
                "add",
                "mysql",
                "--name",
                connection_name,
                "--server",
                MYSQL_HOST,
                "--port",
                str(MYSQL_PORT),
                "--database",
                mysql_db,
                "--username",
                MYSQL_USER,
                "--password",
                MYSQL_PASSWORD,
            )
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            # Verify it appears in list
            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "MySQL" in result.stdout

        finally:
            # Cleanup
            cli_runner("connection", "delete", connection_name, check=False)

    def test_delete_mysql_connection(self, mysql_db, cli_runner):
        """Test deleting a MySQL connection."""
        from .conftest import MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER

        connection_name = "test_delete_mysql"

        # Create connection first
        cli_runner(
            "connections",
            "add",
            "mysql",
            "--name",
            connection_name,
            "--server",
            MYSQL_HOST,
            "--port",
            str(MYSQL_PORT),
            "--database",
            mysql_db,
            "--username",
            MYSQL_USER,
            "--password",
            MYSQL_PASSWORD,
        )

        # Delete it
        result = cli_runner("connection", "delete", connection_name)
        assert result.returncode == 0
        assert "deleted successfully" in result.stdout

        # Verify it's gone
        result = cli_runner("connection", "list")
        assert connection_name not in result.stdout
