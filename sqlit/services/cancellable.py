"""Cancellable query execution for sqlit.

This module provides CancellableQuery which creates a dedicated connection
for query execution that can be cancelled by closing the connection.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..config import ConnectionConfig
    from ..db import DatabaseAdapter
    from .query import NonQueryResult, QueryResult


@dataclass
class CancellableQuery:
    """A query that can be cancelled by closing its dedicated connection.

    Unlike queries run on the shared connection, this creates a dedicated
    connection for each query execution, allowing the query to be cancelled
    by simply closing the connection - which works across all database types.

    Usage:
        query = CancellableQuery(
            sql="SELECT * FROM large_table",
            config=connection_config,
            adapter=db_adapter,
        )

        # In main thread: start cancellable query
        future = executor.submit(query.execute, max_rows=1000)

        # To cancel from another thread:
        query.cancel()  # This closes the connection, aborting the query

    Attributes:
        sql: The SQL query to execute.
        config: Connection configuration for creating dedicated connection.
        adapter: Database adapter for connection and query execution.
    """

    sql: str
    config: ConnectionConfig
    adapter: DatabaseAdapter

    def __post_init__(self) -> None:
        """Initialize internal state."""
        self._connection: Any = None
        self._tunnel: Any = None
        self._lock = threading.Lock()
        self._cancelled = False
        self._executing = False

    def execute(
        self,
        max_rows: int | None = None,
    ) -> QueryResult | NonQueryResult:
        """Execute the query on a dedicated connection.

        Creates a new connection, executes the query, and returns the result.
        The connection is closed after execution (or on cancel).

        Args:
            max_rows: Maximum rows to fetch for SELECT queries.

        Returns:
            QueryResult for SELECT queries, NonQueryResult for others.

        Raises:
            RuntimeError: If already cancelled before execution started.
            Any database-specific errors from connection or query execution.
        """
        from dataclasses import replace

        from ..db import create_ssh_tunnel
        from .query import NonQueryResult, QueryResult, is_select_query

        with self._lock:
            if self._cancelled:
                raise RuntimeError("Query was cancelled")
            self._executing = True

        try:
            # Create SSH tunnel if needed
            self._tunnel, host, port = create_ssh_tunnel(self.config)

            # Adjust config for tunnel
            if self._tunnel:
                connect_config = replace(self.config, server=host, port=str(port))
            else:
                connect_config = self.config

            # Create dedicated connection
            with self._lock:
                if self._cancelled:
                    raise RuntimeError("Query was cancelled")
                self._connection = self.adapter.connect(connect_config)

            # Execute query using adapter methods
            if is_select_query(self.sql):
                columns, rows, truncated = self.adapter.execute_query(self._connection, self.sql, max_rows)
                return QueryResult(
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    truncated=truncated,
                )
            else:
                # Non-SELECT query
                rows_affected = self.adapter.execute_non_query(self._connection, self.sql)
                return NonQueryResult(rows_affected=rows_affected)

        finally:
            self._cleanup()

    def cancel(self) -> bool:
        """Cancel the query by closing the dedicated connection.

        This is safe to call from any thread. If the query is currently
        executing, closing the connection will cause the database driver
        to abort the query (behavior is driver-specific but generally
        raises an exception in the executing thread).

        Returns:
            True if cancellation was initiated, False if already cancelled
            or not yet started.
        """
        with self._lock:
            if self._cancelled:
                return False
            self._cancelled = True

            # If we have a connection, close it to abort the query
            if self._connection is not None:
                try:
                    close_fn = getattr(self._connection, "close", None)
                    if callable(close_fn):
                        close_fn()
                except Exception:
                    pass
                self._connection = None

        return True

    def _cleanup(self) -> None:
        """Clean up resources (connection and tunnel)."""
        with self._lock:
            self._executing = False

            # Close connection
            if self._connection is not None:
                try:
                    close_fn = getattr(self._connection, "close", None)
                    if callable(close_fn):
                        close_fn()
                except Exception:
                    pass
                self._connection = None

            # Stop SSH tunnel
            if self._tunnel is not None:
                try:
                    self._tunnel.stop()
                except Exception:
                    pass
                self._tunnel = None

    @property
    def is_cancelled(self) -> bool:
        """Check if this query has been cancelled."""
        return self._cancelled

    @property
    def is_executing(self) -> bool:
        """Check if this query is currently executing."""
        return self._executing
