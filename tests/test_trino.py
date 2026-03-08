"""Integration tests for Trino database operations."""

from __future__ import annotations

import pytest

from .test_database_base import BaseDatabaseTestsWithLimit, DatabaseTestConfig


class TestTrinoIntegration(BaseDatabaseTestsWithLimit):
    """Integration tests for Trino database operations via CLI."""

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="trino",
            display_name="Trino",
            connection_fixture="trino_connection",
            db_fixture="trino_db",
            create_connection_args=lambda: [],
        )

    def test_primary_key_detection(self, request):
        pytest.skip("Trino connectors do not reliably expose primary keys")
