"""Integration test for multi-statement LIMIT enforcement.

Regression test for https://github.com/fredrikaverpil/sqlit/issues/132:
When running multiple queries with different LIMIT clauses via "Run All",
each result table should have the correct number of rows.

Tests against real MySQL (via Docker) and SQLite to catch driver-specific issues.
"""

from __future__ import annotations

import sqlite3

import pytest

from sqlit.domains.query.app.multi_statement import MultiStatementExecutor
from sqlit.domains.query.app.query_service import (
    KeywordQueryAnalyzer,
    NonQueryResult,
    QueryKind,
    QueryResult,
)


class CursorBasedExecutor:
    """Executor using CursorBasedAdapter's execute_query/execute_non_query logic.

    This mirrors how MultiStatementExecutor calls TransactionExecutor,
    which calls _execute_on_connection, which calls adapter.execute_query.
    The logic is copied verbatim from CursorBasedAdapter to test the exact
    same code path against real database connections.
    """

    def __init__(self, conn) -> None:
        self._conn = conn
        self._analyzer = KeywordQueryAnalyzer()

    def execute(self, sql: str, max_rows: int | None = None) -> QueryResult | NonQueryResult:
        if self._analyzer.classify(sql) == QueryKind.RETURNS_ROWS:
            # Verbatim from CursorBasedAdapter.execute_query
            cursor = self._conn.cursor()
            cursor.execute(sql)
            if cursor.description:
                columns = [col[0] for col in cursor.description]
                if max_rows is not None:
                    rows = cursor.fetchmany(max_rows + 1)
                    truncated = len(rows) > max_rows
                    if truncated:
                        rows = rows[:max_rows]
                else:
                    rows = cursor.fetchall()
                    truncated = False
                return QueryResult(
                    columns=columns,
                    rows=[tuple(row) for row in rows],
                    row_count=len(rows),
                    truncated=truncated,
                )
            return QueryResult(columns=[], rows=[], row_count=0, truncated=False)
        else:
            # Verbatim from CursorBasedAdapter.execute_non_query
            cursor = self._conn.cursor()
            cursor.execute(sql)
            rowcount = int(cursor.rowcount)
            self._conn.commit()
            return NonQueryResult(rows_affected=rowcount)


# ---------------------------------------------------------------------------
# MySQL tests
# ---------------------------------------------------------------------------

def _mysql_connect():
    """Connect to MySQL test instance, skip if unavailable."""
    try:
        import pymysql
    except ImportError:
        pytest.skip("PyMySQL not installed")

    from tests.fixtures.mysql import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD

    try:
        conn = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            connect_timeout=5,
            autocommit=True,
            charset="utf8mb4",
        )
    except Exception as e:
        pytest.skip(f"MySQL not available: {e}")
    return conn


@pytest.fixture
def mysql_limit_db():
    """Create a MySQL test database with enough rows for LIMIT testing."""
    conn = _mysql_connect()
    cursor = conn.cursor()
    cursor.execute("CREATE DATABASE IF NOT EXISTS test_limit_bug")
    cursor.execute("USE test_limit_bug")
    cursor.execute("DROP TABLE IF EXISTS users")
    cursor.execute("CREATE TABLE users (id INT PRIMARY KEY, name VARCHAR(100))")
    for i in range(1, 21):
        cursor.execute("INSERT INTO users (id, name) VALUES (%s, %s)", (i, f"user_{i}"))
    conn.commit()
    yield conn
    cursor = conn.cursor()
    cursor.execute("DROP DATABASE IF EXISTS test_limit_bug")
    conn.close()


class TestMySQLMultiStatementLimits:
    """Test LIMIT enforcement against real MySQL via CursorBasedAdapter."""

    def test_issue_132_limit_2_and_3(self, mysql_limit_db) -> None:
        """Exact reproduction of issue #132: LIMIT 2 and LIMIT 3 on same table."""
        conn = mysql_limit_db
        executor = CursorBasedExecutor(conn)
        multi = MultiStatementExecutor(executor)

        result = multi.execute(
            "SELECT * FROM users LIMIT 2; SELECT * FROM users LIMIT 3;",
            max_rows=100000,
        )

        assert result.completed is True
        assert len(result.results) == 2

        r1 = result.results[0].result
        r2 = result.results[1].result

        assert isinstance(r1, QueryResult)
        assert isinstance(r2, QueryResult)

        assert r1.row_count == 2, (
            f"Issue #132: LIMIT 2 should return 2 rows, got {r1.row_count}"
        )
        assert r2.row_count == 3, (
            f"Issue #132: LIMIT 3 should return 3 rows, got {r2.row_count}"
        )

    def test_limits_5_and_1(self, mysql_limit_db) -> None:
        """LIMIT 5 then LIMIT 1 should return 5 and 1 rows."""
        conn = mysql_limit_db
        executor = CursorBasedExecutor(conn)
        multi = MultiStatementExecutor(executor)

        result = multi.execute(
            "SELECT * FROM users LIMIT 5; SELECT * FROM users LIMIT 1;",
            max_rows=100000,
        )

        assert result.completed is True
        assert result.results[0].result.row_count == 5
        assert result.results[1].result.row_count == 1

    def test_three_different_limits(self, mysql_limit_db) -> None:
        """Three queries with LIMIT 1, 3, 7."""
        conn = mysql_limit_db
        executor = CursorBasedExecutor(conn)
        multi = MultiStatementExecutor(executor)

        result = multi.execute(
            "SELECT * FROM users LIMIT 1; SELECT * FROM users LIMIT 3; SELECT * FROM users LIMIT 7;",
            max_rows=100000,
        )

        assert result.completed is True
        assert len(result.results) == 3
        assert result.results[0].result.row_count == 1
        assert result.results[1].result.row_count == 3
        assert result.results[2].result.row_count == 7

    def test_correct_data_not_mixed(self, mysql_limit_db) -> None:
        """Verify row data is correct, not mixed between results."""
        conn = mysql_limit_db
        executor = CursorBasedExecutor(conn)
        multi = MultiStatementExecutor(executor)

        result = multi.execute(
            "SELECT * FROM users WHERE id <= 2; SELECT * FROM users WHERE id > 18;",
            max_rows=100000,
        )

        assert result.completed is True
        r1_ids = [row[0] for row in result.results[0].result.rows]
        r2_ids = [row[0] for row in result.results[1].result.rows]

        assert r1_ids == [1, 2], f"Expected [1, 2], got {r1_ids}"
        assert r2_ids == [19, 20], f"Expected [19, 20], got {r2_ids}"


class TestMySQLMultiStatementViaTransactionExecutor:
    """Test using the actual TransactionExecutor — the real TUI code path."""

    def test_issue_132_via_transaction_executor(self, mysql_limit_db) -> None:
        """Reproduce #132 using the full TransactionExecutor + MultiStatementExecutor path."""
        from sqlit.domains.connections.providers.registry import get_provider
        from sqlit.domains.query.app.transaction import TransactionExecutor
        from tests.fixtures.mysql import (
            MYSQL_DATABASE,
            MYSQL_HOST,
            MYSQL_PASSWORD,
            MYSQL_PORT,
            MYSQL_USER,
        )
        from tests.helpers import ConnectionConfig

        config = ConnectionConfig(
            name="test-limit-bug",
            db_type="mysql",
            server=MYSQL_HOST,
            port=str(MYSQL_PORT),
            database="test_limit_bug",
            username=MYSQL_USER,
            password=MYSQL_PASSWORD,
        )
        provider = get_provider("mysql")
        executor = TransactionExecutor(config=config, provider=provider)

        try:
            multi = MultiStatementExecutor(executor)
            result = multi.execute(
                "SELECT * FROM users LIMIT 2; SELECT * FROM users LIMIT 3;",
                max_rows=100000,
            )

            assert result.completed is True
            assert len(result.results) == 2

            r1 = result.results[0].result
            r2 = result.results[1].result

            assert isinstance(r1, QueryResult)
            assert isinstance(r2, QueryResult)

            assert r1.row_count == 2, (
                f"Issue #132: LIMIT 2 should return 2 rows, got {r1.row_count}"
            )
            assert r2.row_count == 3, (
                f"Issue #132: LIMIT 3 should return 3 rows, got {r2.row_count}"
            )
        finally:
            executor.close()

    def test_three_limits_via_transaction_executor(self, mysql_limit_db) -> None:
        """Three different LIMITs through TransactionExecutor."""
        from sqlit.domains.connections.providers.registry import get_provider
        from sqlit.domains.query.app.transaction import TransactionExecutor
        from tests.fixtures.mysql import (
            MYSQL_HOST,
            MYSQL_PASSWORD,
            MYSQL_PORT,
            MYSQL_USER,
        )
        from tests.helpers import ConnectionConfig

        config = ConnectionConfig(
            name="test-limit-bug",
            db_type="mysql",
            server=MYSQL_HOST,
            port=str(MYSQL_PORT),
            database="test_limit_bug",
            username=MYSQL_USER,
            password=MYSQL_PASSWORD,
        )
        provider = get_provider("mysql")
        executor = TransactionExecutor(config=config, provider=provider)

        try:
            multi = MultiStatementExecutor(executor)
            result = multi.execute(
                "SELECT * FROM users LIMIT 1; SELECT * FROM users LIMIT 3; SELECT * FROM users LIMIT 7;",
                max_rows=100000,
            )

            assert result.completed is True
            assert len(result.results) == 3
            assert result.results[0].result.row_count == 1
            assert result.results[1].result.row_count == 3
            assert result.results[2].result.row_count == 7
        finally:
            executor.close()


# ---------------------------------------------------------------------------
# SQLite baseline tests (same logic, should always pass)
# ---------------------------------------------------------------------------

@pytest.fixture
def sqlite_limit_db():
    """Create a SQLite test database with enough rows for LIMIT testing."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    for i in range(1, 21):
        conn.execute("INSERT INTO users (id, name) VALUES (?, ?)", (i, f"user_{i}"))
    conn.commit()
    return conn


class TestSQLiteMultiStatementLimits:
    """Baseline: same tests against SQLite to confirm the core logic is correct."""

    def test_issue_132_limit_2_and_3(self, sqlite_limit_db) -> None:
        executor = CursorBasedExecutor(sqlite_limit_db)
        multi = MultiStatementExecutor(executor)

        result = multi.execute(
            "SELECT * FROM users LIMIT 2; SELECT * FROM users LIMIT 3;",
            max_rows=100000,
        )

        assert result.results[0].result.row_count == 2
        assert result.results[1].result.row_count == 3

    def test_limits_5_and_1(self, sqlite_limit_db) -> None:
        executor = CursorBasedExecutor(sqlite_limit_db)
        multi = MultiStatementExecutor(executor)

        result = multi.execute(
            "SELECT * FROM users LIMIT 5; SELECT * FROM users LIMIT 1;",
            max_rows=100000,
        )

        assert result.results[0].result.row_count == 5
        assert result.results[1].result.row_count == 1
