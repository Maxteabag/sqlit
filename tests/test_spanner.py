"""Integration tests for Google Cloud Spanner database operations."""

from __future__ import annotations

import pytest

from tests.test_database_base import BaseDatabaseTestsWithLimit, DatabaseTestConfig


class TestSpannerIntegration(BaseDatabaseTestsWithLimit):
    """Integration tests for Google Cloud Spanner database operations via CLI."""

    @property
    def config(self) -> DatabaseTestConfig:
        from tests.fixtures.spanner import (
            SPANNER_INSTANCE,
            SPANNER_PROJECT,
        )

        return DatabaseTestConfig(
            db_type="spanner",
            display_name="Spanner",
            connection_fixture="spanner_connection",
            db_fixture="spanner_db",
            create_connection_args=lambda db: [
                "--spanner-project",
                SPANNER_PROJECT,
                "--spanner-instance",
                SPANNER_INSTANCE,
                "--database",
                db,
            ],
        )

    def test_create_spanner_connection(self, spanner_db, cli_runner):
        """Test creating a Spanner connection via CLI."""
        from tests.fixtures.spanner import (
            SPANNER_EMULATOR_HOST,
            SPANNER_INSTANCE,
            SPANNER_PROJECT,
        )

        connection_name = "test_create_spanner"

        try:
            # Create connection
            result = cli_runner(
                "connections",
                "add",
                "spanner",
                "--name",
                connection_name,
                "--spanner-project",
                SPANNER_PROJECT,
                "--spanner-instance",
                SPANNER_INSTANCE,
                "--database",
                spanner_db,
                "--spanner-emulator-host",
                SPANNER_EMULATOR_HOST,
            )
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            # Verify it appears in list
            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "Spanner" in result.stdout

        finally:
            # Cleanup
            cli_runner("connection", "delete", connection_name, check=False)

    def test_query_spanner_aggregate(self, spanner_connection, cli_runner):
        """Test aggregate query on Spanner."""
        result = cli_runner(
            "query",
            "-c",
            spanner_connection,
            "-q",
            "SELECT COUNT(*) as cnt FROM test_users",
        )
        assert result.returncode == 0
        assert "3" in result.stdout

    def test_query_spanner_order_by(self, spanner_connection, cli_runner):
        """Test ORDER BY query on Spanner."""
        result = cli_runner(
            "query",
            "-c",
            spanner_connection,
            "-q",
            "SELECT name FROM test_users ORDER BY name",
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "Bob" in result.stdout
        assert "Charlie" in result.stdout

    def test_delete_spanner_connection(self, spanner_db, cli_runner):
        """Test deleting a Spanner connection."""
        from tests.fixtures.spanner import (
            SPANNER_EMULATOR_HOST,
            SPANNER_INSTANCE,
            SPANNER_PROJECT,
        )

        connection_name = "test_delete_spanner"

        # Create connection first
        cli_runner(
            "connections",
            "add",
            "spanner",
            "--name",
            connection_name,
            "--spanner-project",
            SPANNER_PROJECT,
            "--spanner-instance",
            SPANNER_INSTANCE,
            "--database",
            spanner_db,
            "--spanner-emulator-host",
            SPANNER_EMULATOR_HOST,
        )

        # Delete it
        result = cli_runner("connection", "delete", connection_name)
        assert result.returncode == 0
        assert "deleted successfully" in result.stdout

        # Verify it's gone
        result = cli_runner("connection", "list")
        assert connection_name not in result.stdout

    def test_query_spanner_invalid_query(self, spanner_connection, cli_runner):
        """Test handling of invalid SQL query."""
        result = cli_runner(
            "query",
            "-c",
            spanner_connection,
            "-q",
            "SELECT * FROM nonexistent_table",
            check=False,
        )
        assert result.returncode != 0
        assert "error" in result.stdout.lower() or "error" in result.stderr.lower()

    # Skip some base tests that don't apply to Spanner
    @pytest.mark.skip(reason="Spanner doesn't support triggers")
    def test_get_triggers(self, request):
        pass

    @pytest.mark.skip(reason="Spanner doesn't support trigger definitions")
    def test_get_trigger_definition(self, request):
        pass

    @pytest.mark.skip(reason="Spanner doesn't support sequences")
    def test_get_sequences(self, request):
        pass

    @pytest.mark.skip(reason="Spanner doesn't support sequence definitions")
    def test_get_sequence_definition(self, request):
        pass
