"""Query execution service for sqlit.

This module provides a unified query execution service used by both
the TUI and CLI to ensure consistent behavior.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..config import ConnectionConfig
    from .protocols import AdapterProtocol, HistoryStoreProtocol

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


def is_select_query(query: str) -> bool:
    """Determine if a query is a SELECT-type query that returns rows.

    Args:
        query: The SQL query string.

    Returns:
        True if the query starts with a SELECT-like keyword.
    """
    query_type = query.strip().upper().split()[0] if query.strip() else ""
    return query_type in SELECT_KEYWORDS


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
        history_store: Optional history store for saving queries.
            If not provided, uses the default HistoryStore singleton.
    """

    def __init__(self, history_store: HistoryStoreProtocol | None = None):
        """Initialize the query service.

        Args:
            history_store: Optional history store for dependency injection.
        """
        self._history_store = history_store

    def execute(
        self,
        connection: Any,
        adapter: AdapterProtocol,
        query: str,
        config: ConnectionConfig | None = None,
        max_rows: int | None = None,
        save_to_history: bool = True,
    ) -> QueryResult | NonQueryResult:
        """Execute a query and optionally save to history.

        Args:
            connection: The database connection object.
            adapter: The database adapter to use for execution.
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
        if is_select_query(query):
            columns, rows, truncated = adapter.execute_query(connection, query, max_rows)
            result = QueryResult(
                columns=columns,
                rows=list(rows),
                row_count=len(rows),
                truncated=truncated,
            )
        else:
            affected = adapter.execute_non_query(connection, query)
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
        if self._history_store is not None:
            self._history_store.save_query(connection_name, query)
        else:
            # Use default store
            from ..stores import HistoryStore

            HistoryStore.get_instance().save_query(connection_name, query)
