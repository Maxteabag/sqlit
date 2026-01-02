"""Integration tests for SQL transaction support.

These tests verify that manual transactions (BEGIN/COMMIT/ROLLBACK) work correctly
when using the same execution path as the TUI (TransactionExecutor).
"""

from __future__ import annotations

from typing import Any

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


def execute_like_tui_old(config: ConnectionConfig, sql: str) -> QueryResult | int:
    """Execute using OLD TUI behavior (new connection per query).

    This was the BROKEN behavior before TransactionExecutor was integrated.
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


# Global executor to simulate TUI keeping state across queries
_tui_executor: Any = None
_tui_executor_config_name: str | None = None


def execute_like_tui(config: ConnectionConfig, sql: str) -> QueryResult | int:
    """Execute a query using TransactionExecutor, like the TUI now does.

    Uses a persistent TransactionExecutor to maintain transaction state
    across query executions, just like the TUI.

    Returns:
        QueryResult for SELECT queries, rows_affected (int) for non-SELECT.
    """
    from sqlit.domains.query.app.transaction import TransactionExecutor

    global _tui_executor, _tui_executor_config_name

    # Reset executor if config changed
    if _tui_executor is None or _tui_executor_config_name != config.name:
        if _tui_executor is not None:
            _tui_executor.close()
        provider = get_provider(config.db_type)
        _tui_executor = TransactionExecutor(config=config, provider=provider)
        _tui_executor_config_name = config.name

    result = _tui_executor.execute(sql, max_rows=1000)
    if isinstance(result, QueryResult):
        return result
    return result.rows_affected


def reset_tui_executor() -> None:
    """Reset the TUI executor (call between tests)."""
    global _tui_executor, _tui_executor_config_name
    if _tui_executor is not None:
        _tui_executor.close()
        _tui_executor = None
        _tui_executor_config_name = None


@pytest.fixture(autouse=True)
def cleanup_tui_executor():
    """Reset TUI executor before and after each test."""
    reset_tui_executor()
    yield
    reset_tui_executor()


class TestTransactionRollbackLikeTUI:
    """Tests for transaction ROLLBACK using TUI execution path.

    These tests use TransactionExecutor which maintains transaction state
    across query executions, just like the TUI now does.
    """

    @pytest.mark.integration
    def test_rollback_undoes_insert_tui_style(self, postgres_db: str):
        """ROLLBACK should undo an INSERT when executed like TUI."""
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


class TestTransactionExecutor:
    """Tests for TransactionExecutor - the new class that handles transaction-aware execution.

    TransactionExecutor should:
    - Track transaction state (in_transaction)
    - Reuse connection when in transaction mode
    - Create new connections when not in transaction
    - Support atomic batch execution
    """

    @pytest.mark.integration
    def test_rollback_works_with_transaction_executor(self, postgres_db: str):
        """TransactionExecutor should make ROLLBACK actually work."""
        from sqlit.domains.query.app.transaction import TransactionExecutor

        config = make_postgres_config()
        provider = get_provider(config.db_type)
        adapter = get_adapter("postgresql")

        # Setup
        conn = adapter.connect(config)
        try:
            adapter.execute_non_query(conn, "DROP TABLE IF EXISTS tx_executor_test")
            adapter.execute_non_query(
                conn,
                "CREATE TABLE tx_executor_test (id serial PRIMARY KEY, name varchar(100))"
            )
            adapter.execute_non_query(conn, "INSERT INTO tx_executor_test (name) VALUES ('initial')")
        finally:
            conn.close()

        # Use TransactionExecutor
        executor = TransactionExecutor(config, provider)
        try:
            # Get initial count
            result = executor.execute("SELECT COUNT(*) FROM tx_executor_test")
            assert isinstance(result, QueryResult)
            initial_count = result.rows[0][0]
            assert executor.in_transaction is False

            # Begin transaction
            executor.execute("BEGIN")
            assert executor.in_transaction is True

            # Insert (should be in transaction)
            executor.execute("INSERT INTO tx_executor_test (name) VALUES ('should_rollback')")
            assert executor.in_transaction is True

            # Rollback
            executor.execute("ROLLBACK")
            assert executor.in_transaction is False

            # Check final count - should be unchanged
            result = executor.execute("SELECT COUNT(*) FROM tx_executor_test")
            assert isinstance(result, QueryResult)
            final_count = result.rows[0][0]

            assert final_count == initial_count, (
                f"ROLLBACK should have undone the INSERT. "
                f"Initial: {initial_count}, Final: {final_count}"
            )
        finally:
            executor.close()
            # Cleanup
            conn = adapter.connect(config)
            try:
                adapter.execute_non_query(conn, "DROP TABLE IF EXISTS tx_executor_test")
            finally:
                conn.close()

    @pytest.mark.integration
    def test_commit_works_with_transaction_executor(self, postgres_db: str):
        """TransactionExecutor should make COMMIT persist changes.

        This test verifies isolation: uncommitted data should NOT be visible
        from another connection, but after COMMIT it should be visible.
        """
        from sqlit.domains.query.app.transaction import TransactionExecutor

        config = make_postgres_config()
        provider = get_provider(config.db_type)
        adapter = get_adapter("postgresql")

        # Setup
        conn = adapter.connect(config)
        try:
            adapter.execute_non_query(conn, "DROP TABLE IF EXISTS tx_executor_test")
            adapter.execute_non_query(
                conn,
                "CREATE TABLE tx_executor_test (id serial PRIMARY KEY, name varchar(100))"
            )
        finally:
            conn.close()

        # Use TransactionExecutor
        executor = TransactionExecutor(config, provider)
        # Create a separate connection to check isolation
        observer_conn = adapter.connect(config)
        try:
            executor.execute("BEGIN")
            executor.execute("INSERT INTO tx_executor_test (name) VALUES ('uncommitted_row')")

            # BEFORE COMMIT: observer connection should NOT see the row
            cols, rows, _ = adapter.execute_query(
                observer_conn,
                "SELECT COUNT(*) FROM tx_executor_test WHERE name = 'uncommitted_row'"
            )
            count_before_commit = rows[0][0]
            assert count_before_commit == 0, (
                "Uncommitted row should NOT be visible from another connection"
            )

            executor.execute("COMMIT")

            # AFTER COMMIT: observer connection SHOULD see the row
            cols, rows, _ = adapter.execute_query(
                observer_conn,
                "SELECT COUNT(*) FROM tx_executor_test WHERE name = 'uncommitted_row'"
            )
            count_after_commit = rows[0][0]
            assert count_after_commit == 1, (
                "Committed row SHOULD be visible from another connection"
            )
        finally:
            executor.close()
            observer_conn.close()
            conn = adapter.connect(config)
            try:
                adapter.execute_non_query(conn, "DROP TABLE IF EXISTS tx_executor_test")
            finally:
                conn.close()

    @pytest.mark.integration
    def test_atomic_execute_rolls_back_on_error(self, postgres_db: str):
        """atomic_execute should rollback all changes if any statement fails."""
        from sqlit.domains.query.app.transaction import TransactionExecutor

        config = make_postgres_config()
        provider = get_provider(config.db_type)
        adapter = get_adapter("postgresql")

        # Setup
        conn = adapter.connect(config)
        try:
            adapter.execute_non_query(conn, "DROP TABLE IF EXISTS atomic_test")
            adapter.execute_non_query(
                conn,
                "CREATE TABLE atomic_test (id serial PRIMARY KEY, name varchar(100) NOT NULL)"
            )
            adapter.execute_non_query(conn, "INSERT INTO atomic_test (name) VALUES ('initial')")
        finally:
            conn.close()

        executor = TransactionExecutor(config, provider)
        try:
            result = executor.execute("SELECT COUNT(*) FROM atomic_test")
            assert isinstance(result, QueryResult)
            initial_count = result.rows[0][0]

            # This should fail on the second INSERT (NULL not allowed)
            # and rollback the first INSERT too
            query = """
            INSERT INTO atomic_test (name) VALUES ('row1');
            INSERT INTO atomic_test (name) VALUES (NULL);
            """
            with pytest.raises(Exception):
                executor.atomic_execute(query)

            # Count should be unchanged (both inserts rolled back)
            result = executor.execute("SELECT COUNT(*) FROM atomic_test")
            assert isinstance(result, QueryResult)
            final_count = result.rows[0][0]

            assert final_count == initial_count, (
                f"atomic_execute should have rolled back all changes. "
                f"Initial: {initial_count}, Final: {final_count}"
            )
        finally:
            executor.close()
            conn = adapter.connect(config)
            try:
                adapter.execute_non_query(conn, "DROP TABLE IF EXISTS atomic_test")
            finally:
                conn.close()

    @pytest.mark.integration
    def test_atomic_execute_commits_on_success(self, postgres_db: str):
        """atomic_execute should commit all changes if all statements succeed."""
        from sqlit.domains.query.app.transaction import TransactionExecutor

        config = make_postgres_config()
        provider = get_provider(config.db_type)
        adapter = get_adapter("postgresql")

        # Setup
        conn = adapter.connect(config)
        try:
            adapter.execute_non_query(conn, "DROP TABLE IF EXISTS atomic_test")
            adapter.execute_non_query(
                conn,
                "CREATE TABLE atomic_test (id serial PRIMARY KEY, name varchar(100))"
            )
        finally:
            conn.close()

        executor = TransactionExecutor(config, provider)
        try:
            query = """
            INSERT INTO atomic_test (name) VALUES ('row1');
            INSERT INTO atomic_test (name) VALUES ('row2');
            SELECT * FROM atomic_test;
            """
            result = executor.atomic_execute(query)

            # Should return the SELECT result
            assert isinstance(result, QueryResult)
            assert result.row_count == 2
        finally:
            executor.close()
            conn = adapter.connect(config)
            try:
                adapter.execute_non_query(conn, "DROP TABLE IF EXISTS atomic_test")
            finally:
                conn.close()

    @pytest.mark.integration
    def test_connection_reused_during_transaction(self, postgres_db: str):
        """Connection should be reused during a transaction."""
        from sqlit.domains.query.app.transaction import TransactionExecutor

        config = make_postgres_config()
        provider = get_provider(config.db_type)

        executor = TransactionExecutor(config, provider)
        try:
            # Before transaction - no persistent connection
            assert executor._transaction_connection is None

            executor.execute("BEGIN")

            # During transaction - connection should exist
            assert executor._transaction_connection is not None
            conn_id = id(executor._transaction_connection)

            executor.execute("SELECT 1")

            # Same connection should be reused
            assert id(executor._transaction_connection) == conn_id

            executor.execute("COMMIT")

            # After transaction - connection should be closed
            assert executor._transaction_connection is None
        finally:
            executor.close()
