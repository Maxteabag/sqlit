"""Integration tests for IBM Db2 database operations."""

from __future__ import annotations

from .test_database_base import BaseDatabaseTests, DatabaseTestConfig


class TestDb2Integration(BaseDatabaseTests):
    """Integration tests for IBM Db2 database operations via CLI."""

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="db2",
            display_name="IBM Db2",
            connection_fixture="db2_connection",
            db_fixture="db2_db",
            create_connection_args=lambda: [],
            uses_limit=False,
        )
