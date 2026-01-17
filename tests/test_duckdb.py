"""Integration tests for DuckDB database operations."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from .test_database_base import BaseDatabaseTestsWithLimit, DatabaseTestConfig


class TestDuckDBIntegration(BaseDatabaseTestsWithLimit):
    """Integration tests for DuckDB database operations via CLI.

    These tests use a temporary DuckDB database file.
    Tests are skipped if DuckDB is not installed.
    """

    @property
    def config(self) -> DatabaseTestConfig:
        return DatabaseTestConfig(
            db_type="duckdb",
            display_name="DuckDB",
            connection_fixture="duckdb_connection",
            db_fixture="duckdb_db",
            create_connection_args=lambda db: [
                "--file-path",
                str(db),
            ],
            timezone_datetime_type="TIMESTAMPTZ",
        )

    def test_create_duckdb_connection(self, duckdb_db, cli_runner):
        """Test creating a DuckDB connection via CLI."""
        connection_name = "test_create_duckdb"

        try:
            # Create connection
            result = cli_runner(
                "connections",
                "add",
                "duckdb",
                "--name",
                connection_name,
                "--file-path",
                str(duckdb_db),
            )
            assert result.returncode == 0
            assert "created successfully" in result.stdout

            # Verify it appears in list
            result = cli_runner("connection", "list")
            assert connection_name in result.stdout
            assert "DuckDB" in result.stdout

        finally:
            # Cleanup
            cli_runner("connection", "delete", connection_name, check=False)

    def test_query_duckdb_join(self, duckdb_connection, cli_runner):
        """Test JOIN query on DuckDB."""
        result = cli_runner(
            "query",
            "-c",
            duckdb_connection,
            "-q",
            """
                SELECT u.name, p.name as product, p.price
                FROM test_users u
                CROSS JOIN test_products p
                WHERE u.id = 1 AND p.id = 1
            """,
        )
        assert result.returncode == 0
        assert "Alice" in result.stdout
        assert "Widget" in result.stdout

    def test_query_duckdb_update(self, duckdb_connection, cli_runner):
        """Test UPDATE statement on DuckDB."""
        result = cli_runner(
            "query",
            "-c",
            duckdb_connection,
            "-q",
            "UPDATE test_users SET name = 'Alicia' WHERE id = 1",
        )
        assert result.returncode == 0

        # Verify the update
        result = cli_runner(
            "query",
            "-c",
            duckdb_connection,
            "-q",
            "SELECT name FROM test_users WHERE id = 1",
        )
        assert "Alicia" in result.stdout

    def test_delete_duckdb_connection(self, duckdb_db, cli_runner):
        """Test deleting a DuckDB connection."""
        connection_name = "test_delete_duckdb"

        # Create connection first
        cli_runner(
            "connections",
            "add",
            "duckdb",
            "--name",
            connection_name,
            "--file-path",
            str(duckdb_db),
        )

        # Delete it
        result = cli_runner("connection", "delete", connection_name)
        assert result.returncode == 0
        assert "deleted successfully" in result.stdout

        # Verify it's gone
        result = cli_runner("connection", "list")
        assert connection_name not in result.stdout

    def test_query_duckdb_invalid_query(self, duckdb_connection, cli_runner):
        """Test handling of invalid SQL query."""
        result = cli_runner(
            "query",
            "-c",
            duckdb_connection,
            "-q",
            "SELECT * FROM nonexistent_table",
            check=False,
        )
        # Should fail gracefully
        assert result.returncode != 0 or "error" in result.stdout.lower() or "error" in result.stderr.lower()


@pytest.mark.parametrize("use_worker", [True, False])
def test_duckdb_process_worker_no_lock(duckdb_db, use_worker):
    """Ensure DuckDB queries work with or without the process worker."""
    if sys.platform.startswith("win"):
        pytest.skip("DuckDB file-lock behavior differs on Windows")

    from sqlit.domains.connections.app.session import ConnectionSession
    from sqlit.domains.connections.domain.config import ConnectionConfig, FileEndpoint
    from sqlit.domains.process_worker.app.process_worker_client import ProcessWorkerClient
    from sqlit.domains.process_worker.app.support import supports_process_worker
    from sqlit.domains.query.app.transaction import TransactionExecutor

    config = ConnectionConfig(
        name="duckdb_lock_test",
        db_type="duckdb",
        endpoint=FileEndpoint(path=str(duckdb_db)),
    )

    session = ConnectionSession.create(config)
    try:
        outcome = None
        use_worker_effective = bool(use_worker and supports_process_worker(session.provider))
        if use_worker_effective:
            client = ProcessWorkerClient()
            try:
                outcome = client.execute("SELECT 1", config, max_rows=1)
            finally:
                client.close()
        else:
            executor = TransactionExecutor(config=config, provider=session.provider)
            try:
                executor.execute("SELECT 1", max_rows=1)
            finally:
                executor.close()
    finally:
        session.close()

    if use_worker_effective:
        assert outcome is not None
        assert outcome.error is None, f"Unexpected error: {outcome.error}"


def test_duckdb_schema_service_repo_file(tmp_path):
    """Validate explorer schema service against the repo DuckDB fixture."""
    if sys.platform.startswith("win"):
        pytest.skip("DuckDB file-lock behavior differs on Windows")

    from sqlit.domains.connections.app.session import ConnectionSession
    from sqlit.domains.connections.domain.config import ConnectionConfig, FileEndpoint
    from sqlit.domains.explorer.app.schema_service import ExplorerSchemaService
    try:
        import duckdb  # type: ignore
    except Exception:
        pytest.skip("duckdb is not installed")

    db_path = Path(tmp_path) / "cats.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute("CREATE TABLE cats (id INTEGER, name VARCHAR, motto VARCHAR)")
    conn.execute("INSERT INTO cats VALUES (1, 'Mochi', 'Nap hard, snack harder')")
    conn.execute("INSERT INTO cats VALUES (2, 'Nimbus', 'Gravity is optional')")
    conn.close()

    config = ConnectionConfig(
        name="duckdb_repo_fixture",
        db_type="duckdb",
        endpoint=FileEndpoint(path=str(db_path)),
    )

    session = ConnectionSession.create(config)
    try:
        service = ExplorerSchemaService(session=session, object_cache={})
        tables = service.list_folder_items("tables", None)
        table_names = {name for kind, _, name in tables if kind == "table"}
        assert "cats" in table_names

        schema = session.provider.capabilities.default_schema or "main"
        columns = service.list_columns(None, schema, "cats")
        column_names = {col.name for col in columns}
        assert {"id", "name", "motto"}.issubset(column_names)
    finally:
        session.close()
