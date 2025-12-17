"""Integration tests for SQLite database operations."""

from __future__ import annotations

from .test_database_base import BaseDatabaseTestsWithLimit, DatabaseTestConfig


class TestSQLiteIntegration(BaseDatabaseTestsWithLimit):
    """Integration tests for SQLite database operations via CLI."""

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="sqlite",
            display_name="SQLite",
            connection_fixture="sqlite_connection",
            db_fixture="sqlite_db",
            create_connection_args=lambda db: [
                "--file-path",
                str(db),
            ],
        )

    def test_create_sqlite_connection(self, sqlite_db, cli_runner):
        """Test creating a SQLite connection via CLI."""
        connection_name = "test_create_sqlite"

        try:
            # Create connection
            result = cli_runner(
                "connections",
                "add",
                "sqlite",
                "--name",
                connection_name,
                "--file-path",
                str(sqlite_db),
            )
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            # Verify it appears in list
            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "SQLite" in result.stdout

        finally:
            # Cleanup
            cli_runner("connection", "delete", connection_name, check=False)

    def test_query_sqlite_join(self, sqlite_connection, cli_runner):
        """Test JOIN query on SQLite."""
        # This test verifies that complex queries work
        result = cli_runner(
            "query",
            "-c",
            sqlite_connection,
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

    def test_query_sqlite_update(self, sqlite_connection, cli_runner):
        """Test UPDATE statement on SQLite."""
        result = cli_runner(
            "query",
            "-c",
            sqlite_connection,
            "-q",
            "UPDATE test_products SET stock = 200 WHERE id = 1",
        )
        assert result.returncode == 0

        # Verify the update
        result = cli_runner(
            "query",
            "-c",
            sqlite_connection,
            "-q",
            "SELECT stock FROM test_products WHERE id = 1",
        )
        assert "200" in result.stdout

    def test_delete_sqlite_connection(self, sqlite_db, cli_runner):
        """Test deleting a SQLite connection."""
        connection_name = "test_delete_sqlite"

        # Create connection first
        cli_runner(
            "connections",
            "add",
            "sqlite",
            "--name",
            connection_name,
            "--file-path",
            str(sqlite_db),
        )

        # Delete it
        result = cli_runner("connection", "delete", connection_name)
        assert result.returncode == 0
        assert "deleted successfully" in result.stdout

        # Verify it's gone
        result = cli_runner("connection", "list")
        assert connection_name not in result.stdout

    def test_query_sqlite_invalid_query(self, sqlite_connection, cli_runner):
        """Test handling of invalid SQL query."""
        result = cli_runner(
            "query",
            "-c",
            sqlite_connection,
            "-q",
            "SELECT * FROM nonexistent_table",
            check=False,
        )
        assert result.returncode != 0
        assert "error" in result.stdout.lower() or "error" in result.stderr.lower()
