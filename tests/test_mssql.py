"""Integration tests for SQL Server database operations."""

from __future__ import annotations

from .test_database_base import BaseDatabaseTests, DatabaseTestConfig


class TestMSSQLIntegration(BaseDatabaseTests):
    """Integration tests for SQL Server database operations via CLI.

    These tests require a running SQL Server instance (via Docker).
    Tests are skipped if SQL Server is not available.
    """

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="mssql",
            display_name="SQL Server",
            connection_fixture="mssql_connection",
            db_fixture="mssql_db",
            create_connection_args=lambda: [],  # Uses fixtures
            uses_limit=False,  # MSSQL uses TOP instead of LIMIT
        )

    def test_create_mssql_connection(self, mssql_db, cli_runner):
        """Test creating a SQL Server connection via CLI."""
        from .conftest import MSSQL_HOST, MSSQL_PASSWORD, MSSQL_PORT, MSSQL_USER

        connection_name = "test_create_mssql"

        try:
            result = cli_runner(
                "connections",
                "add",
                "mssql",
                "--name",
                connection_name,
                "--server",
                f"{MSSQL_HOST},{MSSQL_PORT}" if MSSQL_PORT != 1433 else MSSQL_HOST,
                "--database",
                mssql_db,
                "--auth-type",
                "sql",
                "--username",
                MSSQL_USER,
                "--password",
                MSSQL_PASSWORD,
            )
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "SQL Server" in result.stdout

        finally:
            cli_runner("connection", "delete", connection_name, check=False)

    def test_query_mssql_top(self, mssql_connection, cli_runner):
        """Test SQL Server specific TOP clause (MSSQL's equivalent of LIMIT)."""
        result = cli_runner(
            "query",
            "-c",
            mssql_connection,
            "-q",
            "SELECT TOP 2 * FROM test_users ORDER BY id",
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "Bob" in result.stdout
        assert "2 row(s) returned" in result.stdout

    def test_delete_mssql_connection(self, mssql_db, cli_runner):
        """Test deleting a SQL Server connection."""
        from .conftest import MSSQL_HOST, MSSQL_PASSWORD, MSSQL_PORT, MSSQL_USER

        connection_name = "test_delete_mssql"

        cli_runner(
            "connections",
            "add",
            "mssql",
            "--name",
            connection_name,
            "--server",
            f"{MSSQL_HOST},{MSSQL_PORT}" if MSSQL_PORT != 1433 else MSSQL_HOST,
            "--database",
            mssql_db,
            "--auth-type",
            "sql",
            "--username",
            MSSQL_USER,
            "--password",
            MSSQL_PASSWORD,
        )

        result = cli_runner("connection", "delete", connection_name)
        assert result.returncode == 0
        assert "deleted successfully" in result.stdout

        result = cli_runner("connection", "list")
        assert connection_name not in result.stdout
