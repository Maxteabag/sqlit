"""Integration tests for Oracle database operations."""

from __future__ import annotations

from .test_database_base import BaseDatabaseTests, DatabaseTestConfig


class TestOracleIntegration(BaseDatabaseTests):
    """Integration tests for Oracle database operations via CLI.

    These tests require a running Oracle instance (via Docker).
    Tests are skipped if Oracle is not available.
    """

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="oracle",
            display_name="Oracle",
            connection_fixture="oracle_connection",
            db_fixture="oracle_db",
            create_connection_args=lambda: [],  # Uses fixtures
            uses_limit=False,  # Oracle uses FETCH FIRST instead of LIMIT
        )

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

    def test_query_oracle_fetch_first(self, oracle_connection, cli_runner):
        """Test Oracle FETCH FIRST clause (Oracle's equivalent of LIMIT)."""
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
