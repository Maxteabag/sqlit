"""Integration tests for ClickHouse database operations."""

from __future__ import annotations

import pytest

from .test_database_base import BaseDatabaseTests, DatabaseTestConfig


class TestClickHouseIntegration(BaseDatabaseTests):
    """Integration tests for ClickHouse database operations via CLI.

    These tests require a running ClickHouse instance (via Docker).
    Tests are skipped if ClickHouse is not available.
    """

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="clickhouse",
            display_name="ClickHouse",
            connection_fixture="clickhouse_connection",
            db_fixture="clickhouse_db",
            create_connection_args=lambda: [],  # Uses fixtures
        )

    def test_create_clickhouse_connection(self, clickhouse_db, cli_runner):
        """Test creating a ClickHouse connection via CLI."""
        from .conftest import (
            CLICKHOUSE_HOST,
            CLICKHOUSE_PASSWORD,
            CLICKHOUSE_PORT,
            CLICKHOUSE_USER,
        )

        connection_name = "test_create_clickhouse"

        try:
            # Create connection
            args = [
                "connections",
                "add",
                "clickhouse",
                "--name",
                connection_name,
                "--server",
                CLICKHOUSE_HOST,
                "--port",
                str(CLICKHOUSE_PORT),
                "--database",
                clickhouse_db,
                "--username",
                CLICKHOUSE_USER,
            ]
            if CLICKHOUSE_PASSWORD:
                args.extend(["--password", CLICKHOUSE_PASSWORD])
            else:
                args.extend(["--password", ""])

            result = cli_runner(*args)
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            # Verify it appears in list
            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "ClickHouse" in result.stdout

        finally:
            # Cleanup
            cli_runner("connection", "delete", connection_name, check=False)

    def test_delete_clickhouse_connection(self, clickhouse_db, cli_runner):
        """Test deleting a ClickHouse connection."""
        from .conftest import (
            CLICKHOUSE_HOST,
            CLICKHOUSE_PASSWORD,
            CLICKHOUSE_PORT,
            CLICKHOUSE_USER,
        )

        connection_name = "test_delete_clickhouse"

        # Create connection first
        args = [
            "connections",
            "add",
            "clickhouse",
            "--name",
            connection_name,
            "--server",
            CLICKHOUSE_HOST,
            "--port",
            str(CLICKHOUSE_PORT),
            "--database",
            clickhouse_db,
            "--username",
            CLICKHOUSE_USER,
        ]
        if CLICKHOUSE_PASSWORD:
            args.extend(["--password", CLICKHOUSE_PASSWORD])
        else:
            args.extend(["--password", ""])

        cli_runner(*args)

        # Delete it
        result = cli_runner("connection", "delete", connection_name)
        assert result.returncode == 0
        assert "deleted successfully" in result.stdout

        # Verify it's gone
        result = cli_runner("connection", "list")
        assert connection_name not in result.stdout
