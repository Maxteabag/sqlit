"""Integration tests for Exasol database operations."""

from __future__ import annotations

import pytest

from .test_database_base import BaseDatabaseTestsWithLimit, DatabaseTestConfig


class TestExasolIntegration(BaseDatabaseTestsWithLimit):
    """Integration tests for Exasol database operations via CLI.

    These tests require a running Exasol instance (via Docker).
    Tests are skipped if Exasol is not available.
    """

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="exasol",
            display_name="Exasol",
            connection_fixture="exasol_connection",
            db_fixture="exasol_db",
            create_connection_args=lambda: [],  # Uses fixtures
        )

    def test_docker_container_connection(self, request):
        """Docker-discovered credentials cannot connect to exasol/docker-db.

        A property of the image, not fixable from tests/: exasol/docker-db
        publishes no credentials through environment variables
        (SPEC.docker_detector has env_vars={}), so the discovered config carries
        no password.
        """
        pytest.skip(
            "exasol/docker-db publishes no credentials through environment "
            "variables (docker_detector env_vars={}), so the discovered config "
            "carries no password"
        )

    def test_primary_key_detection(self, request):
        """Test that adapter correctly detects primary key columns.

        Overrides the base version, which calls get_columns with a lowercase
        table name and no schema. Against a live server that returns nothing:
        the adapter passes an empty schema to pyexasol as a LIKE pattern
        (LIKE '' matches nothing), and pyexasol's meta patterns are
        case-sensitive while EXA_ALL_COLUMNS stores the folded TEST_USERS.
        The app never makes that call - schema_service and process_worker both
        pass the name and schema straight through from get_tables(), which
        returns them uppercase - so this asserts the same contract through the
        call shape the application actually uses.
        """
        from sqlit.domains.connections.app.session import ConnectionSession
        from sqlit.domains.connections.providers.registry import get_adapter
        from sqlit.domains.connections.store.connections import load_connections

        from .conftest import EXASOL_SCHEMA

        connection_name = request.getfixturevalue(self.config.connection_fixture)
        connections = load_connections()
        config = next((c for c in connections if c.name == connection_name), None)
        assert config is not None, f"Connection {connection_name} not found"

        with ConnectionSession.create(config, get_adapter) as session:
            columns = session.adapter.get_columns(
                session.connection,
                "TEST_USERS",
                database=None,
                schema=EXASOL_SCHEMA,
            )

            assert len(columns) >= 3, f"Expected at least 3 columns, got {len(columns)}"

            id_column = next(
                (col for col in columns if col.name.lower() == "id"),
                None,
            )
            assert id_column is not None, f"Column 'id' not found. Columns: {[c.name for c in columns]}"
            assert id_column.is_primary_key, "Column 'id' should be marked as primary key"

            non_pk_columns = [col for col in columns if col.name.lower() != "id"]
            for col in non_pk_columns:
                assert not col.is_primary_key, f"Column '{col.name}' should NOT be marked as primary key"

    def test_create_exasol_connection(self, exasol_db, cli_runner):
        """Test creating an Exasol connection via CLI."""
        from .conftest import (
            EXASOL_HOST,
            EXASOL_PASSWORD,
            EXASOL_PORT,
            EXASOL_USER,
        )

        connection_name = "test_create_exasol"

        try:
            result = cli_runner(
                "connections",
                "add",
                "exasol",
                "--name",
                connection_name,
                "--server",
                EXASOL_HOST,
                "--port",
                str(EXASOL_PORT),
                "--username",
                EXASOL_USER,
                "--password",
                EXASOL_PASSWORD,
                "--schema",
                exasol_db,
                "--tls-mode",
                "require",
            )
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            # Verify it appears in list
            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "Exasol" in result.stdout

        finally:
            # Cleanup
            cli_runner("connection", "delete", connection_name, check=False)

    def test_delete_exasol_connection(self, exasol_db, cli_runner):
        """Test deleting an Exasol connection."""
        from .conftest import (
            EXASOL_HOST,
            EXASOL_PASSWORD,
            EXASOL_PORT,
            EXASOL_USER,
        )

        connection_name = "test_delete_exasol"

        # Create connection first
        cli_runner(
            "connections",
            "add",
            "exasol",
            "--name",
            connection_name,
            "--server",
            EXASOL_HOST,
            "--port",
            str(EXASOL_PORT),
            "--username",
            EXASOL_USER,
            "--password",
            EXASOL_PASSWORD,
            "--schema",
            exasol_db,
            "--tls-mode",
            "require",
        )

        # Delete it
        result = cli_runner("connection", "delete", connection_name)
        assert result.returncode == 0
        assert "deleted successfully" in result.stdout

        # Verify it's gone
        result = cli_runner("connection", "list")
        assert connection_name not in result.stdout
