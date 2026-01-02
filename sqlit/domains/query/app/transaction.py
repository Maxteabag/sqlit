"""Transaction state management and execution for sqlit.

This module provides:
- Detection of transaction control statements (BEGIN, COMMIT, ROLLBACK)
- Transaction state tracking across query executions
- TransactionExecutor for transaction-aware query execution
- Atomic batch execution (all-or-nothing)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .query_service import KeywordQueryAnalyzer, NonQueryResult, QueryKind, QueryResult

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig
    from sqlit.domains.connections.providers.model import DatabaseProvider


# Patterns for detecting transaction control statements
_BEGIN_PATTERN = re.compile(
    r"^\s*(BEGIN|START\s+TRANSACTION)(\s+WORK|\s+TRANSACTION)?\s*;?\s*$",
    re.IGNORECASE,
)

_END_PATTERN = re.compile(
    r"^\s*(COMMIT|ROLLBACK)(\s+WORK|\s+TRANSACTION)?\s*;?\s*$",
    re.IGNORECASE,
)


def is_transaction_start(sql: str) -> bool:
    """Check if SQL statement starts a transaction.

    Detects:
    - BEGIN
    - BEGIN WORK
    - BEGIN TRANSACTION
    - START TRANSACTION
    """
    return bool(_BEGIN_PATTERN.match(sql.strip()))


def is_transaction_end(sql: str) -> bool:
    """Check if SQL statement ends a transaction.

    Detects:
    - COMMIT
    - COMMIT WORK
    - COMMIT TRANSACTION
    - ROLLBACK
    - ROLLBACK WORK
    - ROLLBACK TRANSACTION
    """
    return bool(_END_PATTERN.match(sql.strip()))


def wrap_in_transaction(sql: str) -> str:
    """Wrap SQL in BEGIN/COMMIT for atomic execution.

    If the SQL already starts with BEGIN, it won't be double-wrapped.

    Args:
        sql: SQL statement(s) to wrap.

    Returns:
        SQL wrapped in BEGIN...COMMIT.
    """
    stripped = sql.strip()
    if not stripped:
        return stripped

    # Check if already wrapped - handle "BEGIN;" or "BEGIN" or "START TRANSACTION"
    first_word = stripped.split()[0].upper().rstrip(";") if stripped else ""
    if first_word in ("BEGIN", "START"):
        return stripped

    # Ensure SQL ends with semicolon before adding COMMIT
    if not stripped.endswith(";"):
        stripped += ";"

    return f"BEGIN; {stripped} COMMIT;"


class TransactionStateManager:
    """Tracks transaction state across query executions.

    This class monitors executed queries and maintains state about whether
    we're currently inside a transaction block.
    """

    def __init__(self) -> None:
        self._in_transaction = False

    @property
    def in_transaction(self) -> bool:
        """Whether we're currently inside a transaction."""
        return self._in_transaction

    def on_query_executed(self, sql: str) -> None:
        """Update state after a query is executed.

        Call this after each successful query execution to track
        transaction state changes.

        Args:
            sql: The SQL that was executed.
        """
        from .multi_statement import split_statements

        # Check each statement in multi-statement query
        for statement in split_statements(sql):
            statement = statement.strip()
            if not statement:
                continue

            if is_transaction_start(statement):
                self._in_transaction = True
            elif is_transaction_end(statement):
                self._in_transaction = False

    def reset(self) -> None:
        """Reset transaction state.

        Call this when the connection is closed or reset.
        """
        self._in_transaction = False


@dataclass
class TransactionExecutor:
    """Executes queries with transaction-awareness.

    This executor:
    - Tracks transaction state (BEGIN/COMMIT/ROLLBACK)
    - Reuses connection during a transaction
    - Creates new connections when not in a transaction
    - Supports atomic batch execution

    Usage:
        executor = TransactionExecutor(config, provider)
        try:
            executor.execute("BEGIN")
            executor.execute("INSERT INTO t VALUES (1)")
            executor.execute("COMMIT")  # or ROLLBACK
        finally:
            executor.close()
    """

    config: ConnectionConfig
    provider: DatabaseProvider
    _state: TransactionStateManager | None = None
    _transaction_connection: Any | None = None
    _analyzer: KeywordQueryAnalyzer | None = None

    def __post_init__(self) -> None:
        self._state = TransactionStateManager()
        self._analyzer = KeywordQueryAnalyzer()

    @property
    def in_transaction(self) -> bool:
        """Whether we're currently inside a transaction."""
        return self._state.in_transaction if self._state else False

    def execute(self, sql: str, max_rows: int | None = None) -> QueryResult | NonQueryResult:
        """Execute a query with transaction awareness.

        If we're in a transaction (after BEGIN), reuses the same connection.
        Otherwise, creates a new connection for each query.

        Args:
            sql: SQL to execute.
            max_rows: Maximum rows to fetch for SELECT queries.

        Returns:
            QueryResult for SELECT queries, NonQueryResult for others.
        """
        from .multi_statement import normalize_for_execution, split_statements

        # Normalize SQL: convert blank-line-separated to semicolon-separated
        sql = normalize_for_execution(sql)

        statements = split_statements(sql)
        contains_transaction_start = any(is_transaction_start(statement) for statement in statements)
        in_transaction = bool(self._state and self._state.in_transaction)

        # Get or create connection
        conn = None
        is_temp_connection = False
        use_persistent = (
            self._transaction_connection is not None
            or contains_transaction_start
            or in_transaction
        )

        if use_persistent:
            # Reuse or create a persistent connection for transaction scope
            if self._transaction_connection is None:
                self._transaction_connection = self.provider.connection_factory.connect(self.config)
                try:
                    self.provider.post_connect(self._transaction_connection, self.config)
                except Exception:
                    pass
            conn = self._transaction_connection
        else:
            # Not in transaction - use temporary connection
            conn = self.provider.connection_factory.connect(self.config)
            try:
                self.provider.post_connect(conn, self.config)
            except Exception:
                pass
            is_temp_connection = True

        try:
            # Execute query
            result = self._execute_on_connection(conn, sql, max_rows)

            # Update transaction state
            if self._state:
                self._state.on_query_executed(sql)

            # If transaction ended, close the persistent connection
            if self._transaction_connection is not None and self._state and not self._state.in_transaction:
                self._close_transaction_connection()

            return result

        finally:
            # Close temp connection if we created one and aren't in a transaction
            if is_temp_connection and conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def _execute_on_connection(
        self, conn: Any, sql: str, max_rows: int | None = None
    ) -> QueryResult | NonQueryResult:
        """Execute SQL on a specific connection."""
        if self._analyzer and self._analyzer.classify(sql) == QueryKind.RETURNS_ROWS:
            columns, rows, truncated = self.provider.query_executor.execute_query(
                conn, sql, max_rows
            )
            return QueryResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
                truncated=truncated,
            )
        else:
            rows_affected = self.provider.query_executor.execute_non_query(conn, sql)
            return NonQueryResult(rows_affected=rows_affected)

    def atomic_execute(self, sql: str, max_rows: int | None = None) -> QueryResult | NonQueryResult:
        """Execute SQL atomically (all-or-nothing).

        Wraps the SQL in BEGIN/COMMIT and rolls back on any error.

        Args:
            sql: SQL statement(s) to execute atomically.
            max_rows: Maximum rows to fetch for SELECT queries.

        Returns:
            Result of the last statement.

        Raises:
            Exception: If any statement fails (after rollback).
        """
        from .multi_statement import normalize_for_execution

        # Normalize SQL: convert blank-line-separated to semicolon-separated
        sql = normalize_for_execution(sql)

        # Create a dedicated connection for this atomic operation
        conn = self.provider.connection_factory.connect(self.config)
        try:
            self.provider.post_connect(conn, self.config)
        except Exception:
            pass

        try:
            # Start transaction
            self.provider.query_executor.execute_non_query(conn, "BEGIN")

            # Execute the SQL
            result = self._execute_on_connection(conn, sql, max_rows)

            # Commit
            self.provider.query_executor.execute_non_query(conn, "COMMIT")

            return result

        except Exception:
            # Rollback on any error
            try:
                self.provider.query_executor.execute_non_query(conn, "ROLLBACK")
            except Exception:
                pass
            raise

        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _close_transaction_connection(self) -> None:
        """Close the persistent transaction connection."""
        if self._transaction_connection is not None:
            try:
                self._transaction_connection.close()
            except Exception:
                pass
            self._transaction_connection = None

    def close(self) -> None:
        """Close any open connections and reset state.

        Always call this when done with the executor.
        """
        self._close_transaction_connection()
        if self._state:
            self._state.reset()
