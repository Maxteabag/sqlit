"""Integration tests for Impala database operations.

Notes on Impala quirks:
  * UPDATE and DELETE are not supported on regular (text/parquet) tables. Any
    base-class tests that exercise UPDATE/DELETE will fail loudly on Impala;
    that is expected and the team can choose to override those if/when they
    become mandatory.
  * Impala does not use traditional indexes, triggers, or sequences; the base
    tests for those are gated by adapter capability flags and skip cleanly.
  * Impala uses LIMIT syntax, so this class subclasses BaseDatabaseTestsWithLimit.
"""

from __future__ import annotations

import pytest

from .test_database_base import BaseDatabaseTestsWithLimit, DatabaseTestConfig


class TestImpalaIntegration(BaseDatabaseTestsWithLimit):
    """Integration tests for Impala database operations via CLI.

    These tests require a running Impala instance (via the ``enterprise``
    docker-compose profile). Tests are skipped if Impala is not available.

    Impala has limited support for UPDATE/DELETE on non-Kudu tables, so base
    tests that exercise those paths may fail.
    """

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="impala",
            display_name="Impala",
            connection_fixture="impala_connection",
            db_fixture="impala_db",
            create_connection_args=lambda: [],  # Uses fixtures
        )

    def test_primary_key_detection(self, request):
        """Impala Parquet tables don't carry a PRIMARY KEY constraint; that's a
        Kudu-only feature. The fixture uses Parquet tables, so PK metadata is
        never exposed. Skip to document the divergence.
        """
        pytest.skip(
            "Impala Parquet tables have no PRIMARY KEY constraint; PK metadata "
            "is a Kudu-only feature and not exercised by this fixture."
        )

    def test_create_impala_connection(self, impala_db, cli_runner):
        """Test creating an Impala connection via CLI."""
        from .conftest import (
            IMPALA_AUTH_MECHANISM,
            IMPALA_HOST,
            IMPALA_PORT,
        )

        connection_name = "test_create_impala"

        try:
            # Create connection
            result = cli_runner(
                "connections",
                "add",
                "impala",
                "--name",
                connection_name,
                "--server",
                IMPALA_HOST,
                "--port",
                str(IMPALA_PORT),
                "--database",
                impala_db,
                "--auth-mechanism",
                IMPALA_AUTH_MECHANISM,
            )
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            # Verify it appears in list
            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "Impala" in result.stdout

        finally:
            # Cleanup
            cli_runner("connection", "delete", connection_name, check=False)
