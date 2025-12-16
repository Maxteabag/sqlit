"""Integration tests for Cloudflare D1 database operations."""

from __future__ import annotations

from .test_database_base import BaseDatabaseTestsWithLimit, DatabaseTestConfig


class TestD1Integration(BaseDatabaseTestsWithLimit):
    """Integration tests for Cloudflare D1 database operations via CLI.

    These tests require a running miniflare instance (via Docker).
    Tests are skipped if D1 (miniflare) is not available.
    """

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="d1",
            display_name="Cloudflare D1",
            connection_fixture="d1_connection",
            db_fixture="d1_db",
            create_connection_args=lambda: [],  # Uses fixtures
        )

    def test_create_d1_connection(self, d1_db, cli_runner):
        """Test creating a D1 connection via CLI."""
        from .conftest import D1_ACCOUNT_ID, D1_API_TOKEN

        connection_name = "test_create_d1"

        try:
            # Create connection
            result = cli_runner(
                "connection",
                "create",
                "--name",
                connection_name,
                "--db-type",
                "d1",
                "--host",
                D1_ACCOUNT_ID,
                "--database",
                d1_db,
                "--password",
                D1_API_TOKEN,
            )
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            # Verify it appears in list
            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "Cloudflare D1" in result.stdout

        finally:
            # Cleanup
            cli_runner("connection", "delete", connection_name, check=False)
