"""Query execution service for sqlit.

This module provides a unified query execution service used by both
the TUI and CLI to ensure consistent behavior.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from sqlit.domains.connections.domain.config import ConnectionConfig
    from sqlit.shared.core.protocols import HistoryStoreProtocol, QueryExecutorProtocol

# Query types that return result sets (SELECT-like queries)
SELECT_KEYWORDS = frozenset(["SELECT", "WITH", "SHOW", "DESCRIBE", "EXPLAIN", "PRAGMA"])

# Regex for parsing USE database statements
# Matches: USE dbname, USE [dbname], USE `dbname`, USE "dbname"
_USE_PATTERN = re.compile(
    r"^\s*USE\s+"
    r"(?:"
    r"\[([^\]]+)\]"  # [bracketed] - SQL Server style
    r"|`([^`]+)`"  # `backtick` - MySQL style
    r"|\"([^\"]+)\""  # "quoted" - standard SQL style
    r"|(\w+)"  # unquoted identifier
    r")"
    r"\s*;?\s*$",
    re.IGNORECASE,
)


def parse_use_statement(query: str) -> str | None:
    """Parse a USE database statement and return the database name.

    Supports various quoting styles:
    - USE mydb
    - USE [mydb]  (SQL Server)
    - USE `mydb`  (MySQL)
    - USE "mydb"

    Args:
        query: The SQL query string.

    Returns:
        The database name if this is a USE statement, None otherwise.
    """
    match = _USE_PATTERN.match(query)
    if not match:
        return None
    # Return first non-None group (the captured database name)
    return next((g for g in match.groups() if g is not None), None)


class QueryKind(Enum):
    RETURNS_ROWS = "returns_rows"
    NON_QUERY = "non_query"


class QueryAnalyzer(Protocol):
    def classify(self, query: str) -> QueryKind: ...


class KeywordQueryAnalyzer:
    def classify(self, query: str) -> QueryKind:
        """Classify query based on keyword of the last statement.

        Enhanced for Teradata:
        - Supports SEL (Teradata abbreviation for SELECT)
        - Supports HELP statements
        - Handles LOCKING ... SELECT patterns (common in Teradata)
        """
        from sqlit.domains.query.editing.comments import (
            is_comment_line,
            is_comment_only_statement,
        )

        from .multi_statement import split_statements

        statements = split_statements(query)
        if not statements:
            return QueryKind.NON_QUERY

        # Filter out comment-only statements and find the last actual SQL statement
        for stmt in reversed(statements):
            if is_comment_only_statement(stmt):
                continue
            # Get first non-comment line
            lines = [line.strip() for line in stmt.split("\n") if line.strip()]
            non_comment_lines = [line for line in lines if not is_comment_line(line)]
            if non_comment_lines:
                first_line_upper = non_comment_lines[0].upper()

                # Teradata-specific patterns (word-boundary aware)
                if re.search(r"\b(SELECT|WITH|SHOW|DESCRIBE|EXPLAIN|PRAGMA|SEL|HELP)\b", first_line_upper):
                    return QueryKind.RETURNS_ROWS

                # Fallback to original first-word check
                first_word = first_line_upper.split()[0] if first_line_upper else ""
                return QueryKind.RETURNS_ROWS if first_word in SELECT_KEYWORDS else QueryKind.NON_QUERY

        return QueryKind.NON_QUERY

class DialectQueryAnalyzer:
    def __init__(self, dialect: Any, fallback: QueryAnalyzer | None = None) -> None:
        self._dialect = dialect
        self._fallback = fallback or KeywordQueryAnalyzer()

    def classify(self, query: str) -> QueryKind:
        classifier = getattr(self._dialect, "classify_query", None)
        if callable(classifier):
            result = classifier(query)
            if isinstance(result, QueryKind):
                return result
            if isinstance(result, bool):
                return QueryKind.RETURNS_ROWS if result else QueryKind.NON_QUERY
        return self._fallback.classify(query)


@dataclass
class QueryResult:
    """Result of a SELECT-type query execution."""

    columns: list[str]
    rows: list[tuple]
    row_count: int
    truncated: bool


@dataclass
class NonQueryResult:
    """Result of a non-SELECT query execution (INSERT, UPDATE, DELETE, etc.)."""

    rows_affected: int


class QueryService:
    """Service for executing database queries.

    This service provides a unified interface for query execution,
    handling query type detection, execution, and optional history saving.

    Args:
        history_store: History store for saving queries.
        analyzer: Query analyzer strategy for selecting execution behavior.
    """

    def __init__(self, history_store: HistoryStoreProtocol | None = None, analyzer: QueryAnalyzer | None = None):
        if history_store is None:
            from sqlit.domains.query.store.memory import InMemoryHistoryStore

            history_store = InMemoryHistoryStore()
        self._history_store = history_store
        self._analyzer = analyzer or KeywordQueryAnalyzer()

    def execute(
        self,
        connection: Any,
        executor: QueryExecutorProtocol,
        query: str,
        config: ConnectionConfig | None = None,
        max_rows: int | None = None,
        save_to_history: bool = True,
    ) -> QueryResult | NonQueryResult:
        """Execute a query and optionally save to history.

        Args:
            connection: The database connection object.
            executor: The query executor to use for execution.
            query: The SQL query string to execute.
            config: Optional connection config (needed for history saving).
            max_rows: Optional maximum rows to fetch for SELECT queries.
            save_to_history: Whether to save the query to history.

        Returns:
            QueryResult for SELECT-type queries, NonQueryResult otherwise.

        Raises:
            Any exceptions raised by the underlying database driver.
        """
        result: QueryResult | NonQueryResult
        if self._analyzer.classify(query) == QueryKind.RETURNS_ROWS:
            columns, rows, truncated = executor.execute_query(connection, query, max_rows)
            result = QueryResult(
                columns=columns,
                rows=list(rows),
                row_count=len(rows),
                truncated=truncated,
            )
        else:
            affected = executor.execute_non_query(connection, query)
            result = NonQueryResult(rows_affected=affected)

        # Save to history if requested and config is available
        if save_to_history and config:
            self._save_to_history(config.name, query)

        return result

    def _save_to_history(self, connection_name: str, query: str) -> None:
        """Save a query to history.

        Args:
            connection_name: The name of the connection.
            query: The query string to save.
        """
        self._history_store.save_query(connection_name, query)
