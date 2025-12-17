"""Integration tests for Oracle database operations."""

from __future__ import annotations

import json


class TestOracleIntegration:
    """Integration tests for Oracle database operations via CLI.

    These tests require a running Oracle instance (via Docker).
    Tests are skipped if Oracle is not available.
    """

    def test_create_oracle_connection(self, oracle_db, cli_runner):
        """Test creating an Oracle connection via CLI."""
        from .conftest import ORACLE_HOST, ORACLE_PASSWORD, ORACLE_PORT, ORACLE_USER

        connection_name = "test_create_oracle"

        try:
            # Create connection
            result = cli_runner(
                "connections",
                "add",
                "oracle",
                "--name",
                connection_name,
                "--server",
                ORACLE_HOST,
                "--port",
                str(ORACLE_PORT),
                "--database",
                oracle_db,
                "--username",
                ORACLE_USER,
                "--password",
                ORACLE_PASSWORD,
            )
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            # Verify it appears in list
            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "Oracle" in result.stdout

        finally:
            # Cleanup
            cli_runner("connection", "delete", connection_name, check=False)

    def test_list_connections_shows_oracle(self, oracle_connection, cli_runner):
        """Test that connection list shows Oracle connections correctly."""
        result = cli_runner("connection", "list")
        assert result.returncode == 0
        assert oracle_connection in result.stdout
        assert "Oracle" in result.stdout

    def test_query_oracle_select(self, oracle_connection, cli_runner):
        """Test executing SELECT query on Oracle."""
        result = cli_runner(
            "query",
            "-c",
            oracle_connection,
            "-q",
            "SELECT * FROM test_users ORDER BY id",
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "Bob" in result.stdout
        assert "Charlie" in result.stdout
        assert "3 row(s) returned" in result.stdout

    def test_query_oracle_with_where(self, oracle_connection, cli_runner):
        """Test executing SELECT with WHERE clause on Oracle."""
        result = cli_runner(
            "query",
            "-c",
            oracle_connection,
            "-q",
            "SELECT name, email FROM test_users WHERE id = 1",
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "alice@example.com" in result.stdout
        assert "1 row(s) returned" in result.stdout

    def test_query_oracle_fetch_first(self, oracle_connection, cli_runner):
        """Test Oracle FETCH FIRST clause."""
        result = cli_runner(
            "query",
            "-c",
            oracle_connection,
            "-q",
            "SELECT * FROM test_users ORDER BY id FETCH FIRST 2 ROWS ONLY",
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "Bob" in result.stdout
        assert "2 row(s) returned" in result.stdout

    def test_query_oracle_json_format(self, oracle_connection, cli_runner):
        """Test query output in JSON format."""
        result = cli_runner(
            "query",
            "-c",
            oracle_connection,
            "-q",
            "SELECT id, name FROM test_users ORDER BY id FETCH FIRST 2 ROWS ONLY",
            "--format",
            "json",
        )
        assert result.returncode == 0

        # Parse JSON output (row count message goes to stderr, not stdout)
        data = json.loads(result.stdout)

        assert len(data) == 2
        # Oracle returns column names in uppercase
        assert data[0].get("name") == "Alice" or data[0].get("NAME") == "Alice"
        assert data[1].get("name") == "Bob" or data[1].get("NAME") == "Bob"

    def test_query_oracle_csv_format(self, oracle_connection, cli_runner):
        """Test query output in CSV format."""
        result = cli_runner(
            "query",
            "-c",
            oracle_connection,
            "-q",
            "SELECT id, name FROM test_users ORDER BY id FETCH FIRST 2 ROWS ONLY",
            "--format",
            "csv",
        )
        assert result.returncode == 0
        # Oracle may return uppercase column names
        assert "id,name" in result.stdout.lower() or "ID,NAME" in result.stdout
        assert "Alice" in result.stdout
        assert "Bob" in result.stdout

    def test_query_oracle_view(self, oracle_connection, cli_runner):
        """Test querying a view on Oracle."""
        result = cli_runner(
            "query",
            "-c",
            oracle_connection,
            "-q",
            "SELECT * FROM test_user_emails ORDER BY id",
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "3 row(s) returned" in result.stdout

    def test_query_oracle_aggregate(self, oracle_connection, cli_runner):
        """Test aggregate query on Oracle."""
        result = cli_runner(
            "query",
            "-c",
            oracle_connection,
            "-q",
            "SELECT COUNT(*) as user_count FROM test_users",
        )
        assert result.returncode == 0
        assert "3" in result.stdout

    def test_query_oracle_insert(self, oracle_connection, cli_runner):
        """Test INSERT statement on Oracle."""
        result = cli_runner(
            "query",
            "-c",
            oracle_connection,
            "-q",
            "INSERT INTO test_users (id, name, email) VALUES (4, 'David', 'david@example.com')",
        )
        assert result.returncode == 0

        # Verify the insert
        result = cli_runner(
            "query",
            "-c",
            oracle_connection,
            "-q",
            "SELECT * FROM test_users WHERE id = 4",
        )
        assert "David" in result.stdout

    def test_delete_oracle_connection(self, oracle_db, cli_runner):
        """Test deleting an Oracle connection."""
        from .conftest import ORACLE_HOST, ORACLE_PASSWORD, ORACLE_PORT, ORACLE_USER

        connection_name = "test_delete_oracle"

        # Create connection first
        cli_runner(
            "connections",
            "add",
            "oracle",
            "--name",
            connection_name,
            "--server",
            ORACLE_HOST,
            "--port",
            str(ORACLE_PORT),
            "--database",
            oracle_db,
            "--username",
            ORACLE_USER,
            "--password",
            ORACLE_PASSWORD,
        )

        # Delete it
        result = cli_runner("connection", "delete", connection_name)
        assert result.returncode == 0
        assert "deleted successfully" in result.stdout

        # Verify it's gone
        result = cli_runner("connection", "list")
        assert connection_name not in result.stdout
