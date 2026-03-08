"""Integration tests for Oracle 11g legacy database operations."""

from __future__ import annotations

from .test_database_base import BaseDatabaseTests, DatabaseTestConfig


class TestOracleLegacyIntegration(BaseDatabaseTests):
    """Integration tests for Oracle 11g legacy database operations via CLI."""

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="oracle_legacy",
            display_name="Oracle Legacy",
            connection_fixture="oracle11g_connection",
            db_fixture="oracle11g_db",
            create_connection_args=lambda: [],
            uses_limit=False,
        )

    def test_query_oracle_legacy_rownum(self, oracle11g_connection, cli_runner):
        result = cli_runner(
            "query",
            "-c",
            oracle11g_connection,
            "-q",
            "SELECT * FROM (SELECT * FROM test_users ORDER BY id) WHERE ROWNUM <= 2",
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "Bob" in result.stdout
        assert "2 row(s) returned" in result.stdout
