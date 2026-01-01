"""Integration tests for SQL transaction support.

These tests verify that manual transactions (BEGIN/COMMIT/ROLLBACK) work correctly
when using the same execution path as the TUI (CancellableQuery).
"""

from __future__ import annotations

import pytest

from sqlit.domains.connections.providers.registry import get_adapter, get_provider
from sqlit.domains.query.app.cancellable import CancellableQuery
from sqlit.domains.query.app.query_service import (
    KeywordQueryAnalyzer,
    QueryKind,
    QueryResult,
)
from tests.fixtures.postgres import (
    POSTGRES_DATABASE,
    POSTGRES_HOST,
    POSTGRES_PASSWORD,
    POSTGRES_PORT,
    POSTGRES_USER,
)
from tests.helpers import ConnectionConfig


def make_postgres_config() -> ConnectionConfig:
    return ConnectionConfig(
        name="test-transactions",
        db_type="postgresql",
        server=POSTGRES_HOST,
        port=str(POSTGRES_PORT),
        database=POSTGRES_DATABASE,
        username=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )


def execute_like_tui(config: ConnectionConfig, sql: str) -> QueryResult | int:
    """Execute a query using CancellableQuery, exactly like the TUI does.

    Each call creates a new connection, executes the query, and closes the connection.
    This mirrors the TUI behavior in query_execution.py.

    Returns:
        QueryResult for SELECT queries, rows_affected (int) for non-SELECT.
    """
    provider = get_provider(config.db_type)
    cancellable = CancellableQuery(
        sql=sql,
        config=config,
        provider=provider,
    )
    result = cancellable.execute(max_rows=1000)
    if isinstance(result, QueryResult):
        return result
    return result.rows_affected


class TestTransactionRollbackLikeTUI:
    """Tests for transaction ROLLBACK using TUI execution path.

    These tests use CancellableQuery which creates a new connection per query,
    exactly like the TUI does. This reveals the bug where transactions don't
    persist across separate query executions.
    """

    @pytest.mark.integration
    def test_rollback_undoes_insert_tui_style(self, postgres_db: str):
        """ROLLBACK should undo an INSERT when executed like TUI.

        This test currently FAILS because each query runs on a new connection,
        so the transaction state is lost between BEGIN and ROLLBACK.
        """
        config = make_postgres_config()
        adapter = get_adapter("postgresql")

        # Setup: use direct connection for table creation
        conn = adapter.connect(config)
        try:
            adapter.execute_non_query(conn, "DROP TABLE IF EXISTS transaction_test")
            adapter.execute_non_query(
                conn,
                "CREATE TABLE transaction_test (id serial PRIMARY KEY, name varchar(100))"
            )
            adapter.execute_non_query(conn, "INSERT INTO transaction_test (name) VALUES ('initial')")
        finally:
            conn.close()

        # Get initial count using TUI-style execution
        result = execute_like_tui(config, "SELECT COUNT(*) FROM transaction_test")
        assert isinstance(result, QueryResult)
        initial_count = result.rows[0][0]

        # Execute transaction commands TUI-style (each on separate connection)
        execute_like_tui(config, "BEGIN")
        execute_like_tui(config, "INSERT INTO transaction_test (name) VALUES ('should_rollback')")
        execute_like_tui(config, "ROLLBACK")

        # Check final count
        result = execute_like_tui(config, "SELECT COUNT(*) FROM transaction_test")
        assert isinstance(result, QueryResult)
        final_count = result.rows[0][0]

        assert final_count == initial_count, (
            f"ROLLBACK should have undone the INSERT. "
            f"Initial: {initial_count}, Final: {final_count}"
        )

        # Cleanup
        conn = adapter.connect(config)
        try:
            adapter.execute_non_query(conn, "DROP TABLE IF EXISTS transaction_test")
        finally:
            conn.close()

    @pytest.mark.integration
    def test_commit_persists_insert_tui_style(self, postgres_db: str):
        """COMMIT should persist an INSERT when executed like TUI."""
        config = make_postgres_config()
        adapter = get_adapter("postgresql")

        # Setup
        conn = adapter.connect(config)
        try:
            adapter.execute_non_query(conn, "DROP TABLE IF EXISTS transaction_test")
            adapter.execute_non_query(
                conn,
                "CREATE TABLE transaction_test (id serial PRIMARY KEY, name varchar(100))"
            )
            adapter.execute_non_query(conn, "INSERT INTO transaction_test (name) VALUES ('initial')")
        finally:
            conn.close()

        # Get initial count
        result = execute_like_tui(config, "SELECT COUNT(*) FROM transaction_test")
        assert isinstance(result, QueryResult)
        initial_count = result.rows[0][0]

        # Execute transaction commands TUI-style
        execute_like_tui(config, "BEGIN")
        execute_like_tui(config, "INSERT INTO transaction_test (name) VALUES ('should_persist')")
        execute_like_tui(config, "COMMIT")

        # Check final count
        result = execute_like_tui(config, "SELECT COUNT(*) FROM transaction_test")
        assert isinstance(result, QueryResult)
        final_count = result.rows[0][0]

        # With TUI-style execution, the INSERT auto-commits anyway (no real transaction)
        # so this test passes but for the wrong reason
        assert final_count == initial_count + 1

        # Cleanup
        conn = adapter.connect(config)
        try:
            adapter.execute_non_query(conn, "DROP TABLE IF EXISTS transaction_test")
        finally:
            conn.close()


class TestTransactionWithSharedConnection:
    """Tests for transactions using a shared connection (how it SHOULD work)."""

    @pytest.mark.integration
    def test_rollback_undoes_insert_shared_connection(self, postgres_db: str):
        """ROLLBACK works correctly when using a shared connection."""
        config = make_postgres_config()
        adapter = get_adapter("postgresql")
        conn = adapter.connect(config)

        try:
            adapter.execute_non_query(conn, "DROP TABLE IF EXISTS transaction_test")
            adapter.execute_non_query(
                conn,
                "CREATE TABLE transaction_test (id serial PRIMARY KEY, name varchar(100))"
            )
            adapter.execute_non_query(conn, "INSERT INTO transaction_test (name) VALUES ('initial')")

            cols, rows, _ = adapter.execute_query(conn, "SELECT COUNT(*) FROM transaction_test")
            initial_count = rows[0][0]

            adapter.execute_non_query(conn, "BEGIN")
            adapter.execute_non_query(conn, "INSERT INTO transaction_test (name) VALUES ('should_rollback')")
            adapter.execute_non_query(conn, "ROLLBACK")

            cols, rows, _ = adapter.execute_query(conn, "SELECT COUNT(*) FROM transaction_test")
            final_count = rows[0][0]

            assert final_count == initial_count, (
                f"ROLLBACK should have undone the INSERT. "
                f"Initial: {initial_count}, Final: {final_count}"
            )
        finally:
            try:
                adapter.execute_non_query(conn, "DROP TABLE IF EXISTS transaction_test")
                conn.close()
            except Exception:
                pass


class TestMultiStatementQueryClassification:
    """Tests for multi-statement query classification."""

    def test_multi_statement_ending_in_select_classified_as_returns_rows(self):
        """Multi-statement query ending in SELECT should be classified as RETURNS_ROWS."""
        analyzer = KeywordQueryAnalyzer()

        query = """
        BEGIN;
        INSERT INTO test (name) VALUES ('test');
        SELECT * FROM test;
        """

        result = analyzer.classify(query)
        assert result == QueryKind.RETURNS_ROWS

    def test_single_select_classified_as_returns_rows(self):
        """Single SELECT should be classified as RETURNS_ROWS."""
        analyzer = KeywordQueryAnalyzer()
        result = analyzer.classify("SELECT * FROM test")
        assert result == QueryKind.RETURNS_ROWS

    def test_single_insert_classified_as_non_query(self):
        """Single INSERT should be classified as NON_QUERY."""
        analyzer = KeywordQueryAnalyzer()
        result = analyzer.classify("INSERT INTO test (name) VALUES ('test')")
        assert result == QueryKind.NON_QUERY

    @pytest.mark.integration
    def test_multi_statement_as_single_query_works(self, postgres_db: str):
        """Multi-statement query executed as single query should work atomically."""
        config = make_postgres_config()
        adapter = get_adapter("postgresql")

        # Setup
        conn = adapter.connect(config)
        try:
            adapter.execute_non_query(conn, "DROP TABLE IF EXISTS multi_stmt_test")
            adapter.execute_non_query(
                conn,
                "CREATE TABLE multi_stmt_test (id serial PRIMARY KEY, name varchar(100))"
            )
            adapter.execute_non_query(conn, "INSERT INTO multi_stmt_test (name) VALUES ('existing')")
        finally:
            conn.close()

        # Execute multi-statement query as single execution (this works!)
        query = """
        BEGIN;
        INSERT INTO multi_stmt_test (name) VALUES ('new_row');
        SELECT * FROM multi_stmt_test;
        """
        result = execute_like_tui(config, query)

        assert isinstance(result, QueryResult)
        assert len(result.columns) > 0
        assert result.row_count > 0

        # Cleanup
        conn = adapter.connect(config)
        try:
            adapter.execute_non_query(conn, "DROP TABLE IF EXISTS multi_stmt_test")
        finally:
            conn.close()


class TestTransactionIsolation:
    """Tests for transaction isolation."""

    @pytest.mark.integration
    def test_uncommitted_changes_not_visible_from_other_connection(self, postgres_db: str):
        """Uncommitted changes should not be visible from another connection."""
        config = make_postgres_config()
        adapter = get_adapter("postgresql")
        conn1 = adapter.connect(config)
        conn2 = adapter.connect(config)

        try:
            adapter.execute_non_query(conn1, "DROP TABLE IF EXISTS isolation_test")
            adapter.execute_non_query(
                conn1,
                "CREATE TABLE isolation_test (id serial PRIMARY KEY, name varchar(100))"
            )

            adapter.execute_non_query(conn1, "BEGIN")
            adapter.execute_non_query(conn1, "INSERT INTO isolation_test (name) VALUES ('uncommitted')")

            # Check from second connection - should not see uncommitted row
            cols, rows, _ = adapter.execute_query(
                conn2,
                "SELECT COUNT(*) FROM isolation_test WHERE name = 'uncommitted'"
            )
            count = rows[0][0]

            assert count == 0, "Uncommitted row should not be visible from another connection"

            adapter.execute_non_query(conn1, "ROLLBACK")

        finally:
            try:
                adapter.execute_non_query(conn1, "DROP TABLE IF EXISTS isolation_test")
                conn1.close()
                conn2.close()
            except Exception:
                pass
