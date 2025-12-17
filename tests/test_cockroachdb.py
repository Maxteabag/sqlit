"""Integration tests for CockroachDB database operations."""

from __future__ import annotations

from .test_database_base import BaseDatabaseTestsWithLimit, DatabaseTestConfig


class TestCockroachDBIntegration(BaseDatabaseTestsWithLimit):
    """Integration tests for CockroachDB database operations via CLI.

    These tests require a running CockroachDB instance (via Docker).
    Tests are skipped if CockroachDB is not available.
    """

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="cockroachdb",
            display_name="CockroachDB",
            connection_fixture="cockroachdb_connection",
            db_fixture="cockroachdb_db",
            create_connection_args=lambda: [],  # Uses fixtures
        )

    def test_create_cockroachdb_connection(self, cockroachdb_db, cli_runner):
        """Test creating a CockroachDB connection via CLI."""
        from .conftest import (
            COCKROACHDB_HOST,
            COCKROACHDB_PASSWORD,
            COCKROACHDB_PORT,
            COCKROACHDB_USER,
        )

        connection_name = "test_create_cockroachdb"

        try:
            args = [
                "connections",
                "add",
                "cockroachdb",
                "--name",
                connection_name,
                "--server",
                COCKROACHDB_HOST,
                "--port",
                str(COCKROACHDB_PORT),
                "--database",
                cockroachdb_db,
                "--username",
                COCKROACHDB_USER,
                "--password",
                COCKROACHDB_PASSWORD or "",
            ]
            result = cli_runner(*args)
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            # Verify it appears in list
            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "CockroachDB" in result.stdout

        finally:
            # Cleanup
            cli_runner("connection", "delete", connection_name, check=False)

    def test_delete_cockroachdb_connection(self, cockroachdb_db, cli_runner):
        """Test deleting a CockroachDB connection."""
        from .conftest import (
            COCKROACHDB_HOST,
            COCKROACHDB_PASSWORD,
            COCKROACHDB_PORT,
            COCKROACHDB_USER,
        )

        connection_name = "test_delete_cockroachdb"

        args = [
            "connections",
            "add",
            "cockroachdb",
            "--name",
            connection_name,
            "--server",
            COCKROACHDB_HOST,
            "--port",
            str(COCKROACHDB_PORT),
            "--database",
            cockroachdb_db,
            "--username",
            COCKROACHDB_USER,
            "--password",
            COCKROACHDB_PASSWORD or "",
        ]
        cli_runner(*args)

        # Delete it
        result = cli_runner("connection", "delete", connection_name)
        assert result.returncode == 0
        assert "deleted successfully" in result.stdout

        # Verify it's gone
        result = cli_runner("connection", "list")
        assert connection_name not in result.stdout
