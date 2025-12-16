"""Integration tests for DuckDB database operations."""

from __future__ import annotations

from .test_database_base import BaseDatabaseTestsWithLimit, DatabaseTestConfig


class TestDuckDBIntegration(BaseDatabaseTestsWithLimit):
    """Integration tests for DuckDB database operations via CLI.

    These tests use a temporary DuckDB database file.
    Tests are skipped if DuckDB is not installed.
    """

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="duckdb",
            display_name="DuckDB",
            connection_fixture="duckdb_connection",
            db_fixture="duckdb_db",
            create_connection_args=lambda db: [
                "--db-type",
                "duckdb",
                "--file-path",
                str(db),
            ],
        )

    def test_create_duckdb_connection(self, duckdb_db, cli_runner):
        """Test creating a DuckDB connection via CLI."""
        connection_name = "test_create_duckdb"

        try:
            # Create connection
            result = cli_runner(
                "connection",
                "create",
                "--name",
                connection_name,
                "--db-type",
                "duckdb",
                "--file-path",
                str(duckdb_db),
            )
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            # Verify it appears in list
            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "DuckDB" in result.stdout

        finally:
            # Cleanup
            cli_runner("connection", "delete", connection_name, check=False)

    def test_query_duckdb_join(self, duckdb_connection, cli_runner):
        """Test JOIN query on DuckDB."""
        result = cli_runner(
            "query",
            "-c",
            duckdb_connection,
            "-q",
            """
                SELECT u.name, p.name as product, p.price
                FROM test_users u
                CROSS JOIN test_products p
                WHERE u.id = 1 AND p.id = 1
            """,
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "Widget" in result.stdout

    def test_query_duckdb_update(self, duckdb_connection, cli_runner):
        """Test UPDATE statement on DuckDB."""
        result = cli_runner(
            "query",
            "-c",
            duckdb_connection,
            "-q",
            "UPDATE test_users SET name = 'Alicia' WHERE id = 1",
        )
        assert result.returncode == 0

        # Verify the update
        result = cli_runner(
            "query",
            "-c",
            duckdb_connection,
            "-q",
            "SELECT name FROM test_users WHERE id = 1",
        )
        assert "Alicia" in result.stdout

    def test_delete_duckdb_connection(self, duckdb_db, cli_runner):
        """Test deleting a DuckDB connection."""
        connection_name = "test_delete_duckdb"

        # Create connection first
        cli_runner(
            "connection",
            "create",
            "--name",
            connection_name,
            "--db-type",
            "duckdb",
            "--file-path",
            str(duckdb_db),
        )

        # Delete it
        result = cli_runner("connection", "delete", connection_name)
        assert result.returncode == 0
        assert "deleted successfully" in result.stdout

        # Verify it's gone
        result = cli_runner("connection", "list")
        assert connection_name not in result.stdout

    def test_query_duckdb_invalid_query(self, duckdb_connection, cli_runner):
        """Test handling of invalid SQL query."""
        result = cli_runner(
            "query",
            "-c",
            duckdb_connection,
            "-q",
            "SELECT * FROM nonexistent_table",
            check=False,
        )
        # Should fail gracefully
        assert result.returncode != 0 or "error" in result.stdout.lower() or "error" in result.stderr.lower()
