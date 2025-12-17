"""Integration tests for SQL Server database operations."""

from __future__ import annotations

import json


class TestMSSQLIntegration:
    """Integration tests for SQL Server database operations via CLI.

    These tests require a running SQL Server instance (via Docker).
    Tests are skipped if SQL Server is not available.
    """

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

    def test_list_connections_shows_mssql(self, mssql_connection, cli_runner):
        """Test that connection list shows SQL Server connections correctly."""
        result = cli_runner("connection", "list")
        assert result.returncode == 0
        assert mssql_connection in result.stdout
        assert "SQL Server" in result.stdout

    def test_query_mssql_select(self, mssql_connection, cli_runner):
        """Test executing SELECT query on SQL Server."""
        result = cli_runner(
            "query",
            "-c",
            mssql_connection,
            "-q",
            "SELECT * FROM test_users ORDER BY id",
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "Bob" in result.stdout
        assert "Charlie" in result.stdout
        assert "3 row(s) returned" in result.stdout

    def test_query_mssql_with_where(self, mssql_connection, cli_runner):
        """Test executing SELECT with WHERE clause on SQL Server."""
        result = cli_runner(
            "query",
            "-c",
            mssql_connection,
            "-q",
            "SELECT name, email FROM test_users WHERE id = 1",
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "alice@example.com" in result.stdout
        assert "1 row(s) returned" in result.stdout

    def test_query_mssql_top(self, mssql_connection, cli_runner):
        """Test SQL Server specific TOP clause."""
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

    def test_query_mssql_json_format(self, mssql_connection, cli_runner):
        """Test query output in JSON format."""
        result = cli_runner(
            "query",
            "-c",
            mssql_connection,
            "-q",
            "SELECT TOP 2 id, name FROM test_users ORDER BY id",
            "--format",
            "json",
        )
        assert result.returncode == 0

        # Parse JSON output (row count message goes to stderr, not stdout)
        data = json.loads(result.stdout)

        assert len(data) == 2
        assert data[0]["name"] == "Alice"
        assert data[1]["name"] == "Bob"

    def test_query_mssql_csv_format(self, mssql_connection, cli_runner):
        """Test query output in CSV format."""
        result = cli_runner(
            "query",
            "-c",
            mssql_connection,
            "-q",
            "SELECT TOP 2 id, name FROM test_users ORDER BY id",
            "--format",
            "csv",
        )
        assert result.returncode == 0
        assert "id,name" in result.stdout
        assert "1,Alice" in result.stdout
        assert "2,Bob" in result.stdout

    def test_query_mssql_view(self, mssql_connection, cli_runner):
        """Test querying a view on SQL Server."""
        result = cli_runner(
            "query",
            "-c",
            mssql_connection,
            "-q",
            "SELECT * FROM test_user_emails ORDER BY id",
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "3 row(s) returned" in result.stdout

    def test_query_mssql_aggregate(self, mssql_connection, cli_runner):
        """Test aggregate query on SQL Server."""
        result = cli_runner(
            "query",
            "-c",
            mssql_connection,
            "-q",
            "SELECT COUNT(*) as user_count FROM test_users",
        )
        assert result.returncode == 0
        assert "3" in result.stdout

    def test_query_mssql_insert(self, mssql_connection, cli_runner):
        """Test INSERT statement on SQL Server."""
        result = cli_runner(
            "query",
            "-c",
            mssql_connection,
            "-q",
            "INSERT INTO test_users (id, name, email) VALUES (4, 'David', 'david@example.com')",
        )
        assert result.returncode == 0

        # Verify the insert
        result = cli_runner(
            "query",
            "-c",
            mssql_connection,
            "-q",
            "SELECT * FROM test_users WHERE id = 4",
        )
        assert "David" in result.stdout

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
