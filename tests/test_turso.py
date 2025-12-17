"""Integration tests for Turso (libSQL) database operations."""

from __future__ import annotations

from .test_database_base import BaseDatabaseTestsWithLimit, DatabaseTestConfig


class TestTursoIntegration(BaseDatabaseTestsWithLimit):
    """Integration tests for Turso database operations via CLI.

    These tests require a running libsql-server instance (via Docker).
    Tests are skipped if libsql-server is not available.
    """

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="turso",
            display_name="Turso",
            connection_fixture="turso_connection",
            db_fixture="turso_db",
            create_connection_args=lambda: [],  # Uses fixtures
        )

    def test_create_turso_connection(self, turso_db, cli_runner):
        """Test creating a Turso connection via CLI."""
        connection_name = "test_create_turso"

        try:
            result = cli_runner(
                "connection",
                "create",
                "--name",
                connection_name,
                "--db-type",
                "turso",
                "--server",
                turso_db,
                "--password",
                "",
            )
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "Turso" in result.stdout

        finally:
            cli_runner("connection", "delete", connection_name, check=False)

    def test_query_turso_join(self, turso_connection, cli_runner):
        """Test JOIN query on Turso."""
        result = cli_runner(
            "query",
            "-c",
            turso_connection,
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

    def test_query_turso_update(self, turso_connection, cli_runner):
        """Test UPDATE statement on Turso."""
        result = cli_runner(
            "query",
            "-c",
            turso_connection,
            "-q",
            "UPDATE test_products SET stock = 200 WHERE id = 1",
        )
        assert result.returncode == 0

        result = cli_runner(
            "query",
            "-c",
            turso_connection,
            "-q",
            "SELECT stock FROM test_products WHERE id = 1",
        )
        assert "200" in result.stdout

    def test_delete_turso_connection(self, turso_db, cli_runner):
        """Test deleting a Turso connection."""
        connection_name = "test_delete_turso"

        cli_runner(
            "connection",
            "create",
            "--name",
            connection_name,
            "--db-type",
            "turso",
            "--server",
            turso_db,
            "--password",
            "",
        )

        result = cli_runner("connection", "delete", connection_name)
        assert result.returncode == 0
        assert "deleted successfully" in result.stdout

        result = cli_runner("connection", "list")
        assert connection_name not in result.stdout

    def test_query_turso_invalid_query(self, turso_connection, cli_runner):
        """Test handling of invalid SQL query."""
        result = cli_runner(
            "query",
            "-c",
            turso_connection,
            "-q",
            "SELECT * FROM nonexistent_table",
            check=False,
        )
        assert result.returncode != 0
        assert "error" in result.stdout.lower() or "error" in result.stderr.lower()
