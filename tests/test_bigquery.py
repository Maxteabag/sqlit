"""Integration tests for BigQuery database operations."""

from __future__ import annotations

import pytest

from .test_database_base import BaseDatabaseTestsWithLimit, DatabaseTestConfig


class TestBigQueryIntegration(BaseDatabaseTestsWithLimit):
    """Integration tests for BigQuery database operations via CLI.

    These tests require a running BigQuery emulator.
    Tests are skipped if BigQuery emulator is not available.
    """

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="bigquery",
            display_name="BigQuery",
            connection_fixture="bigquery_connection",
            db_fixture="bigquery_db",
            create_connection_args=lambda: [],
        )

    def test_primary_key_detection(self, request):
        pytest.skip("BigQuery emulator does not expose primary key metadata")

    # The following tests are overridden because the BigQuery emulator does not
    # support DELETE operations. Data accumulates during test runs.

    def test_query_select(self, request, cli_runner):
        """Test executing SELECT query.

        Overridden for BigQuery: emulator doesn't support DELETE, so row count
        may be higher than 3 if insert tests ran before this test.
        """
        connection = request.getfixturevalue(self.config.connection_fixture)
        result = cli_runner(
            "query",
            "-c",
            connection,
            "-q",
            "SELECT * FROM test_users ORDER BY id",
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "Bob" in result.stdout
        assert "Charlie" in result.stdout
        # Don't check exact row count - emulator can't delete old data
        assert "row(s) returned" in result.stdout

    def test_query_view(self, request, cli_runner):
        """Test querying a view.

        Overridden for BigQuery: emulator doesn't support DELETE, so row count
        may be higher than 3 if insert tests ran before this test.
        """
        connection = request.getfixturevalue(self.config.connection_fixture)
        result = cli_runner(
            "query",
            "-c",
            connection,
            "-q",
            "SELECT * FROM test_user_emails ORDER BY id",
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "example.com" in result.stdout
        # Don't check exact row count - emulator can't delete old data
        assert "row(s) returned" in result.stdout

    def test_query_aggregate(self, request, cli_runner):
        """Test aggregate query.

        Overridden for BigQuery: emulator doesn't support DELETE, so row count
        may be higher than 3 if insert tests ran before this test.
        """
        connection = request.getfixturevalue(self.config.connection_fixture)
        result = cli_runner(
            "query",
            "-c",
            connection,
            "-q",
            "SELECT COUNT(*) as user_count FROM test_users",
        )
        assert result.returncode == 0
        # Don't check exact count - emulator can't delete old data
        assert "user_count" in result.stdout
        assert "1 row(s) returned" in result.stdout

    def test_cancellable_query_select(self, request):
        """Test CancellableQuery execution (used by TUI).

        Overridden for BigQuery: emulator doesn't support DELETE, so row count
        may be higher than 3 if insert tests ran before this test.
        """
        from sqlit.domains.connections.providers.catalog import get_provider
        from sqlit.domains.connections.store.connections import load_connections
        from sqlit.domains.query.app.cancellable import CancellableQuery
        from sqlit.domains.query.app.query_service import QueryResult

        connection_name = request.getfixturevalue(self.config.connection_fixture)
        connections = load_connections()
        config = next((c for c in connections if c.name == connection_name), None)
        assert config is not None

        provider = get_provider(self.config.db_type)

        query = CancellableQuery(
            sql="SELECT * FROM test_users ORDER BY id",
            config=config,
            provider=provider,
        )
        result = query.execute(max_rows=100)

        assert isinstance(result, QueryResult)
        assert len(result.columns) >= 2
        # BigQuery emulator doesn't support DELETE, so rows accumulate
        assert len(result.rows) >= 3
        row_values = [str(v) for v in result.rows[0]]
        assert "Alice" in row_values

    def test_streaming_json_output(self, request, cli_runner):
        """Test JSON output works for BigQuery adapter.

        Overridden for BigQuery: emulator doesn't support DELETE, so row count
        may be higher than 3 if insert tests ran before this test.
        """
        import json

        connection = request.getfixturevalue(self.config.connection_fixture)
        result = cli_runner(
            "query",
            "-c",
            connection,
            "-q",
            "SELECT id, name FROM test_users ORDER BY id",
            "--format",
            "json",
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        # BigQuery emulator doesn't support DELETE, so rows accumulate
        assert len(data) >= 3
        first_name = data[0].get("name") or data[0].get("NAME")
        assert first_name == "Alice"

    def test_query_service_execution(self, request):
        """Test QueryService execution path.

        Overridden for BigQuery: emulator doesn't support DELETE, so row count
        may be higher than 3 if insert tests ran before this test.
        """
        from sqlit.domains.connections.app.session import ConnectionSession
        from sqlit.domains.connections.providers.registry import get_adapter
        from sqlit.domains.connections.store.connections import load_connections
        from sqlit.domains.query.app.query_service import QueryResult, QueryService

        connection_name = request.getfixturevalue(self.config.connection_fixture)
        connections = load_connections()
        config = next((c for c in connections if c.name == connection_name), None)
        assert config is not None

        service = QueryService()

        with ConnectionSession.create(config, get_adapter) as session:
            result = service.execute(
                connection=session.connection,
                executor=session.provider.query_executor,
                query="SELECT * FROM test_users ORDER BY id",
                config=config,
                max_rows=100,
                save_to_history=False,
            )

            assert isinstance(result, QueryResult)
            # BigQuery emulator doesn't support DELETE, so rows accumulate
            assert len(result.rows) >= 3
            row_values = [str(v) for v in result.rows[0]]
            assert "Alice" in row_values

    def test_create_bigquery_connection(self, bigquery_db, cli_runner):
        """Test creating a BigQuery connection via CLI."""
        from .conftest import BIGQUERY_LOCATION, BIGQUERY_PROJECT

        connection_name = "test_create_bigquery"

        try:
            result = cli_runner(
                "connections",
                "add",
                "bigquery",
                "--name",
                connection_name,
                "--server",
                BIGQUERY_PROJECT,
                "--database",
                bigquery_db,
                "--bigquery-location",
                BIGQUERY_LOCATION,
            )
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "BigQuery" in result.stdout

        finally:
            cli_runner("connection", "delete", connection_name, check=False)

    def test_delete_bigquery_connection(self, bigquery_db, cli_runner):
        """Test deleting a BigQuery connection."""
        from .conftest import BIGQUERY_LOCATION, BIGQUERY_PROJECT

        connection_name = "test_delete_bigquery"

        cli_runner(
            "connections",
            "add",
            "bigquery",
            "--name",
            connection_name,
            "--server",
            BIGQUERY_PROJECT,
            "--database",
            bigquery_db,
            "--bigquery-location",
            BIGQUERY_LOCATION,
        )

        result = cli_runner("connection", "delete", connection_name)
        assert result.returncode == 0
        assert "deleted successfully" in result.stdout

        result = cli_runner("connection", "list")
        assert connection_name not in result.stdout
