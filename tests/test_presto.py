"""Integration tests for Presto database operations."""

from __future__ import annotations

import pytest

from .test_database_base import BaseDatabaseTestsWithLimit, DatabaseTestConfig


class TestPrestoIntegration(BaseDatabaseTestsWithLimit):
    """Integration tests for Presto database operations via CLI."""

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="presto",
            display_name="Presto",
            connection_fixture="presto_connection",
            db_fixture="presto_db",
            create_connection_args=lambda: [],
        )

    def test_primary_key_detection(self, request):
        pytest.skip("Presto connectors do not reliably expose primary keys")
