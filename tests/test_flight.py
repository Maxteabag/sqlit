"""Integration tests for Apache Arrow Flight SQL database operations."""

from __future__ import annotations

from .test_database_base import BaseDatabaseTestsWithLimit, DatabaseTestConfig


class TestFlightIntegration(BaseDatabaseTestsWithLimit):
    """Integration tests for Flight SQL database operations via CLI.

    These tests require a running Flight SQL server (via Docker).
    Tests are skipped if Flight SQL is not available.

    Uses voltrondata/sqlflite Docker image which provides a Flight SQL
    server backed by DuckDB with a small TPC-H dataset.
    """

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="flight",
            display_name="Arrow Flight SQL",
            connection_fixture="flight_connection",
            db_fixture="flight_db",
            create_connection_args=lambda: [],  # Uses fixtures
            uses_limit=True,  # Flight SQL uses standard LIMIT syntax
        )

    def test_create_flight_connection(self, flight_db, cli_runner):
        """Test creating a Flight SQL connection via CLI."""
        from .conftest import FLIGHT_HOST, FLIGHT_PASSWORD, FLIGHT_PORT

        connection_name = "test_create_flight"

        try:
            # Create connection
            result = cli_runner(
                "connections",
                "add",
                "flight",
                "--name",
                connection_name,
                "--server",
                FLIGHT_HOST,
                "--port",
                str(FLIGHT_PORT),
                "--password",
                FLIGHT_PASSWORD,
            )
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            # Verify it appears in list
            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "Flight" in result.stdout

        finally:
            # Cleanup
            cli_runner("connection", "delete", connection_name, check=False)

    def test_delete_flight_connection(self, flight_db, cli_runner):
        """Test deleting a Flight SQL connection."""
        from .conftest import FLIGHT_HOST, FLIGHT_PASSWORD, FLIGHT_PORT

        connection_name = "test_delete_flight"

        # Create connection first
        cli_runner(
            "connections",
            "add",
            "flight",
            "--name",
            connection_name,
            "--server",
            FLIGHT_HOST,
            "--port",
            str(FLIGHT_PORT),
            "--password",
            FLIGHT_PASSWORD,
        )

        # Delete it
        result = cli_runner("connection", "delete", connection_name)
        assert result.returncode == 0
        assert "deleted successfully" in result.stdout

        # Verify it's gone
        result = cli_runner("connection", "list")
        assert connection_name not in result.stdout
