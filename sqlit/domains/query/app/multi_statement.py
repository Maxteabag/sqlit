"""Multi-statement query execution for sqlit.

This module provides:
- Statement splitting (handling strings with semicolons)
- Multi-statement execution with stop-on-error
- Result collection from multiple statements
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from .query_service import NonQueryResult, QueryResult


def _iter_sql_chars(sql: str) -> Iterator[tuple[int, str, bool]]:
    """Iterate through SQL characters, tracking string literal context.

    Handles escape sequences (backslash) and SQL-style doubled quotes.

    Yields:
        (index, char, outside_string) tuples where outside_string is True
        when the character is not inside a string literal.
    """
    in_single_quote = False
    in_double_quote = False
    i = 0

    while i < len(sql):
        char = sql[i]

        # Handle escape sequences in strings
        if i + 1 < len(sql) and char == "\\" and (in_single_quote or in_double_quote):
            yield (i, char, False)
            yield (i + 1, sql[i + 1], False)
            i += 2
            continue

        # Handle doubled quotes (SQL escape for quotes)
        if char == "'" and i + 1 < len(sql) and sql[i + 1] == "'" and in_single_quote:
            yield (i, "'", False)
            yield (i + 1, "'", False)
            i += 2
            continue
        if char == '"' and i + 1 < len(sql) and sql[i + 1] == '"' and in_double_quote:
            yield (i, '"', False)
            yield (i + 1, '"', False)
            i += 2
            continue

        # Toggle quote state and yield
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            yield (i, char, False)  # Quote char is part of string syntax
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            yield (i, char, False)  # Quote char is part of string syntax
        else:
            yield (i, char, not in_single_quote and not in_double_quote)

        i += 1


def _has_semicolon_outside_strings(sql: str) -> bool:
    """Check if SQL has semicolons outside of string literals."""
    for _, char, outside in _iter_sql_chars(sql):
        if char == ";" and outside:
            return True
    return False


def _split_by_semicolons(sql: str) -> list[str]:
    """Split SQL by semicolons, respecting string literals."""
    statements = []
    current: list[str] = []

    for _, char, outside in _iter_sql_chars(sql):
        if char == ";" and outside:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(char)

    # Don't forget the last statement (may not end with semicolon)
    stmt = "".join(current).strip()
    if stmt:
        statements.append(stmt)

    return statements


def _split_by_blank_lines(sql: str) -> list[str]:
    """Split SQL by blank lines, respecting string literals.

    A blank line is defined as a line containing only whitespace.
    This is triggered when there are no semicolons in the query.
    """
    statements = []
    current: list[str] = []
    line_start = 0
    prev_line_empty = False

    for idx, char, outside in _iter_sql_chars(sql):
        if char == "\n" and outside:
            line_content = sql[line_start:idx]
            current_line_empty = not line_content.strip()

            if current_line_empty and prev_line_empty:
                # Consecutive blank lines, skip
                pass
            elif current_line_empty and current:
                # Blank line after content - split here
                stmt = "".join(current).strip()
                if stmt:
                    statements.append(stmt)
                current = []
            else:
                # Regular newline, keep it
                current.append(char)

            prev_line_empty = current_line_empty
            line_start = idx + 1
        else:
            current.append(char)
            if char not in " \t\n":
                prev_line_empty = False

    # Don't forget the last statement
    stmt = "".join(current).strip()
    if stmt:
        statements.append(stmt)

    return statements


def _append_statement_range(
    ranges: list[tuple[str, int, int]], sql: str, stmt_start: int, stmt_end: int
) -> None:
    """Helper to append a statement range, calculating actual positions."""
    stmt_full = sql[stmt_start:stmt_end]
    stmt_text = stmt_full.strip()
    if stmt_text:
        actual_start = stmt_start + (len(stmt_full) - len(stmt_full.lstrip()))
        ranges.append((stmt_text, actual_start, actual_start + len(stmt_text)))


def _get_statement_ranges(sql: str) -> list[tuple[str, int, int]]:
    """Get statements with their character ranges in the original SQL.

    Splitting strategy (matches split_statements):
    1. If query contains semicolons (outside strings) → split by semicolons
    2. If no semicolons but has blank lines → split by blank lines
    3. Otherwise → return as single statement

    Returns:
        List of (statement_text, start_offset, end_offset) tuples.
        Offsets are 0-based character positions in the original SQL string.
    """
    if not sql or not sql.strip():
        return []

    ranges: list[tuple[str, int, int]] = []

    # Strategy 1: If semicolons exist, use semicolon splitting with tracking
    if _has_semicolon_outside_strings(sql):
        stmt_start = 0

        for idx, char, outside in _iter_sql_chars(sql):
            if char == ";" and outside:
                _append_statement_range(ranges, sql, stmt_start, idx)
                stmt_start = idx + 1

        _append_statement_range(ranges, sql, stmt_start, len(sql))
        return ranges

    # Strategy 2: If blank lines exist, use blank line splitting with tracking
    if re.search(r"\n\s*\n", sql):
        stmt_start = 0
        line_start = 0
        prev_line_empty = False

        for idx, char, outside in _iter_sql_chars(sql):
            if char == "\n" and outside:
                line_content = sql[line_start:idx]
                current_line_empty = not line_content.strip()

                if current_line_empty and prev_line_empty:
                    # Consecutive blank lines, skip
                    pass
                elif current_line_empty:
                    # Blank line after content - this is a statement boundary
                    _append_statement_range(ranges, sql, stmt_start, idx)
                    stmt_start = idx + 1

                prev_line_empty = current_line_empty
                line_start = idx + 1
            elif char not in " \t\n":
                prev_line_empty = False

        _append_statement_range(ranges, sql, stmt_start, len(sql))
        return ranges

    # Strategy 3: Single statement
    stripped = sql.strip()
    if stripped:
        start_offset = len(sql) - len(sql.lstrip())
        return [(stripped, start_offset, len(sql))]

    return []


def find_statement_at_cursor(sql: str, row: int, col: int) -> tuple[str, int, int] | None:
    """Find the SQL statement containing the cursor position.

    Args:
        sql: Full SQL text (may contain multiple statements).
        row: Cursor row (0-based line number).
        col: Cursor column (0-based character position within the line).

    Returns:
        Tuple of (statement_text, start_char_offset, end_char_offset) or None if not found.
    """
    if not sql:
        return None

    # Convert (row, col) to absolute character offset
    lines = sql.split("\n")
    if row >= len(lines):
        # Cursor is past end of text, use last position
        cursor_offset = len(sql)
    else:
        # Sum lengths of all previous lines plus newline characters
        cursor_offset = sum(len(lines[i]) + 1 for i in range(row)) + col

    ranges = _get_statement_ranges(sql)

    if not ranges:
        return None

    # Find the statement containing the cursor
    for stmt_text, start, end in ranges:
        if start <= cursor_offset <= end:
            return (stmt_text, start, end)

    # If cursor is between statements or at the very end,
    # return the nearest preceding statement
    for stmt_text, start, end in reversed(ranges):
        if cursor_offset >= start:
            return (stmt_text, start, end)

    # Fallback to first statement
    return ranges[0] if ranges else None


def split_statements(sql: str) -> list[str]:
    """Split SQL into individual statements.

    Splitting strategy:
    1. If query contains semicolons (outside strings) → split by semicolons
    2. If no semicolons but has blank lines → split by blank lines
    3. Otherwise → return as single statement

    Handles:
    - Multiple statements separated by semicolons
    - Multiple statements separated by blank lines (when no semicolons)
    - Semicolons/blank lines inside string literals (preserved)
    - Empty statements (filtered out)
    - Trailing semicolons

    Args:
        sql: SQL containing one or more statements.

    Returns:
        List of individual SQL statements.
    """
    if not sql or not sql.strip():
        return []

    # Strategy 1: If semicolons exist, use semicolon splitting
    if _has_semicolon_outside_strings(sql):
        return _split_by_semicolons(sql)

    # Strategy 2: If blank lines exist, use blank line splitting
    # A blank line is two consecutive newlines (possibly with whitespace between)
    if re.search(r"\n\s*\n", sql):
        return _split_by_blank_lines(sql)

    # Strategy 3: Single statement
    return [sql.strip()]


def normalize_for_execution(sql: str) -> str:
    """Normalize SQL for database execution.

    Converts blank-line-separated statements to semicolon-separated,
    since databases expect semicolons between statements.

    Args:
        sql: SQL that may use blank lines or semicolons as separators.

    Returns:
        SQL with semicolons between statements (ready for database execution).
    """
    if not sql or not sql.strip():
        return sql

    # If already has semicolons, return as-is
    if _has_semicolon_outside_strings(sql):
        return sql

    # If has blank lines, split and rejoin with semicolons
    if re.search(r"\n\s*\n", sql):
        statements = _split_by_blank_lines(sql)
        if len(statements) > 1:
            return "; ".join(statements)

    # Single statement, return as-is
    return sql


@dataclass
class StatementResult:
    """Result from executing a single statement."""

    statement: str
    result: QueryResult | NonQueryResult | None
    success: bool
    error: str | None = None


@dataclass
class MultiStatementResult:
    """Result from executing multiple statements."""

    results: list[StatementResult] = field(default_factory=list)
    completed: bool = True
    error_index: int | None = None

    @property
    def has_error(self) -> bool:
        """Whether any statement failed."""
        return self.error_index is not None

    @property
    def successful_count(self) -> int:
        """Number of statements that executed successfully."""
        return sum(1 for r in self.results if r.success)

    @property
    def query_results(self) -> list[QueryResult]:
        """Get all QueryResult objects from successful statements."""
        from .query_service import QueryResult

        return [
            r.result
            for r in self.results
            if r.success and isinstance(r.result, QueryResult)
        ]


class MultiStatementExecutor:
    """Executes multiple SQL statements with stop-on-error behavior.

    This executor:
    - Splits SQL into individual statements
    - Executes each statement sequentially
    - Stops on first error
    - Collects results from all executed statements

    Usage:
        executor = MultiStatementExecutor(query_executor)
        result = executor.execute("INSERT INTO t VALUES (1); SELECT * FROM t")
        for stmt_result in result.results:
            print(stmt_result.statement, stmt_result.success)
    """

    def __init__(self, query_executor: Any) -> None:
        """Initialize the executor.

        Args:
            query_executor: An executor with an `execute(sql)` method that returns
                           QueryResult or NonQueryResult.
        """
        self._executor = query_executor

    def execute(self, sql: str, max_rows: int | None = None) -> MultiStatementResult:
        """Execute multiple SQL statements.

        Statements are executed sequentially. Execution stops on first error.

        Args:
            sql: SQL containing one or more statements separated by semicolons.
            max_rows: Maximum rows to fetch for SELECT queries.

        Returns:
            MultiStatementResult containing results from all executed statements.
        """
        statements = split_statements(sql)

        if not statements:
            return MultiStatementResult(results=[], completed=True, error_index=None)

        results: list[StatementResult] = []

        for i, statement in enumerate(statements):
            try:
                # Execute the statement
                if max_rows is not None:
                    result = self._executor.execute(statement, max_rows=max_rows)
                else:
                    result = self._executor.execute(statement)

                results.append(
                    StatementResult(
                        statement=statement,
                        result=result,
                        success=True,
                        error=None,
                    )
                )

            except Exception as e:
                # Record the error and stop
                results.append(
                    StatementResult(
                        statement=statement,
                        result=None,
                        success=False,
                        error=str(e),
                    )
                )
                return MultiStatementResult(
                    results=results,
                    completed=False,
                    error_index=i,
                )

        return MultiStatementResult(
            results=results,
            completed=True,
            error_index=None,
        )
