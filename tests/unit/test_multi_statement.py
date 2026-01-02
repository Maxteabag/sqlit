"""Unit tests for multi-statement query execution.

These tests define the expected behavior for executing multiple SQL statements
in a single query, including error handling and result collection.
"""

from __future__ import annotations

import pytest


class TestStatementSplitting:
    """Tests for splitting multi-statement queries."""

    def test_splits_simple_statements(self):
        """Should split statements by semicolon."""
        from sqlit.domains.query.app.multi_statement import split_statements

        query = "SELECT 1; SELECT 2; SELECT 3"
        statements = split_statements(query)

        assert len(statements) == 3
        assert statements[0].strip() == "SELECT 1"
        assert statements[1].strip() == "SELECT 2"
        assert statements[2].strip() == "SELECT 3"

    def test_handles_trailing_semicolon(self):
        """Should handle trailing semicolon without creating empty statement."""
        from sqlit.domains.query.app.multi_statement import split_statements

        query = "SELECT 1; SELECT 2;"
        statements = split_statements(query)

        assert len(statements) == 2

    def test_handles_single_statement(self):
        """Should handle single statement without semicolon."""
        from sqlit.domains.query.app.multi_statement import split_statements

        query = "SELECT * FROM users"
        statements = split_statements(query)

        assert len(statements) == 1
        assert statements[0].strip() == "SELECT * FROM users"

    def test_handles_empty_query(self):
        """Should return empty list for empty query."""
        from sqlit.domains.query.app.multi_statement import split_statements

        assert split_statements("") == []
        assert split_statements("   ") == []

    def test_preserves_semicolons_in_strings(self):
        """Should not split on semicolons inside string literals."""
        from sqlit.domains.query.app.multi_statement import split_statements

        query = "INSERT INTO t (x) VALUES ('a;b'); SELECT 1"
        statements = split_statements(query)

        assert len(statements) == 2
        assert "a;b" in statements[0]

    def test_handles_multiline_statements(self):
        """Should handle statements spanning multiple lines."""
        from sqlit.domains.query.app.multi_statement import split_statements

        query = """
        SELECT *
        FROM users
        WHERE id = 1;

        SELECT *
        FROM orders
        """
        statements = split_statements(query)

        assert len(statements) == 2


class TestMultiStatementResult:
    """Tests for MultiStatementResult data structure."""

    def test_creates_result_with_multiple_items(self):
        """Should create result containing multiple statement results."""
        from sqlit.domains.query.app.multi_statement import (
            MultiStatementResult,
            StatementResult,
        )
        from sqlit.domains.query.app.query_service import NonQueryResult, QueryResult

        results = MultiStatementResult(
            results=[
                StatementResult(
                    statement="INSERT INTO t VALUES (1)",
                    result=NonQueryResult(rows_affected=1),
                    success=True,
                ),
                StatementResult(
                    statement="SELECT * FROM t",
                    result=QueryResult(columns=["id"], rows=[(1,)], row_count=1, truncated=False),
                    success=True,
                ),
            ],
            completed=True,
            error_index=None,
        )

        assert len(results.results) == 2
        assert results.completed is True
        assert results.error_index is None

    def test_marks_error_index_on_failure(self):
        """Should mark which statement failed."""
        from sqlit.domains.query.app.multi_statement import (
            MultiStatementResult,
            StatementResult,
        )
        from sqlit.domains.query.app.query_service import NonQueryResult

        results = MultiStatementResult(
            results=[
                StatementResult(
                    statement="INSERT INTO t VALUES (1)",
                    result=NonQueryResult(rows_affected=1),
                    success=True,
                ),
                StatementResult(
                    statement="INSERT INTO t VALUES (NULL)",
                    result=None,
                    success=False,
                    error="NOT NULL constraint failed",
                ),
            ],
            completed=False,
            error_index=1,
        )

        assert results.completed is False
        assert results.error_index == 1
        assert results.results[1].error == "NOT NULL constraint failed"


class TestMultiStatementExecutor:
    """Tests for MultiStatementExecutor behavior."""

    def test_executes_all_statements_on_success(self):
        """Should execute all statements when none fail."""
        from unittest.mock import MagicMock

        from sqlit.domains.query.app.multi_statement import MultiStatementExecutor
        from sqlit.domains.query.app.query_service import NonQueryResult, QueryResult

        mock_executor = MagicMock()
        mock_executor.execute.side_effect = [
            NonQueryResult(rows_affected=1),
            NonQueryResult(rows_affected=1),
            QueryResult(columns=["count"], rows=[(2,)], row_count=1, truncated=False),
        ]

        executor = MultiStatementExecutor(mock_executor)
        query = "INSERT INTO t VALUES (1); INSERT INTO t VALUES (2); SELECT COUNT(*) FROM t"
        result = executor.execute(query)

        assert len(result.results) == 3
        assert result.completed is True
        assert mock_executor.execute.call_count == 3

    def test_stops_on_first_error(self):
        """Should stop execution on first error."""
        from unittest.mock import MagicMock

        from sqlit.domains.query.app.multi_statement import MultiStatementExecutor
        from sqlit.domains.query.app.query_service import NonQueryResult

        mock_executor = MagicMock()
        mock_executor.execute.side_effect = [
            NonQueryResult(rows_affected=1),
            Exception("Column does not exist"),
            NonQueryResult(rows_affected=1),  # Should not be reached
        ]

        executor = MultiStatementExecutor(mock_executor)
        query = "INSERT INTO t VALUES (1); SELECT bad_column FROM t; INSERT INTO t VALUES (2)"
        result = executor.execute(query)

        assert len(result.results) == 2  # Only 2 statements attempted
        assert result.completed is False
        assert result.error_index == 1
        assert mock_executor.execute.call_count == 2  # Third not called

    def test_returns_single_result_for_single_statement(self):
        """Single statement should still work."""
        from unittest.mock import MagicMock

        from sqlit.domains.query.app.multi_statement import MultiStatementExecutor
        from sqlit.domains.query.app.query_service import QueryResult

        mock_executor = MagicMock()
        mock_executor.execute.return_value = QueryResult(
            columns=["id"], rows=[(1,)], row_count=1, truncated=False
        )

        executor = MultiStatementExecutor(mock_executor)
        result = executor.execute("SELECT * FROM t")

        assert len(result.results) == 1
        assert result.completed is True

    def test_handles_empty_query(self):
        """Empty query should return empty result."""
        from unittest.mock import MagicMock

        from sqlit.domains.query.app.multi_statement import MultiStatementExecutor

        mock_executor = MagicMock()
        executor = MultiStatementExecutor(mock_executor)
        result = executor.execute("")

        assert len(result.results) == 0
        assert result.completed is True
        assert mock_executor.execute.call_count == 0

    def test_collects_all_select_results(self):
        """Should collect results from all SELECT statements."""
        from unittest.mock import MagicMock

        from sqlit.domains.query.app.multi_statement import MultiStatementExecutor
        from sqlit.domains.query.app.query_service import QueryResult

        mock_executor = MagicMock()
        mock_executor.execute.side_effect = [
            QueryResult(columns=["a"], rows=[(1,)], row_count=1, truncated=False),
            QueryResult(columns=["b"], rows=[(2,)], row_count=1, truncated=False),
        ]

        executor = MultiStatementExecutor(mock_executor)
        result = executor.execute("SELECT 1 AS a; SELECT 2 AS b")

        assert len(result.results) == 2
        assert result.results[0].result.columns == ["a"]
        assert result.results[1].result.columns == ["b"]

    def test_preserves_statement_text_in_results(self):
        """Should preserve the original statement text in results."""
        from unittest.mock import MagicMock

        from sqlit.domains.query.app.multi_statement import MultiStatementExecutor
        from sqlit.domains.query.app.query_service import NonQueryResult

        mock_executor = MagicMock()
        mock_executor.execute.return_value = NonQueryResult(rows_affected=1)

        executor = MultiStatementExecutor(mock_executor)
        result = executor.execute("INSERT INTO users (name) VALUES ('Alice')")

        assert result.results[0].statement == "INSERT INTO users (name) VALUES ('Alice')"


class TestBlankLineSplitting:
    """Tests for splitting statements by blank lines when no semicolons."""

    def test_splits_by_blank_line_when_no_semicolons(self):
        """Should split by blank lines when query has no semicolons."""
        from sqlit.domains.query.app.multi_statement import split_statements

        query = """SELECT * FROM vikings

SELECT * FROM ships

SELECT * FROM weapons"""
        statements = split_statements(query)

        assert len(statements) == 3
        assert "vikings" in statements[0]
        assert "ships" in statements[1]
        assert "weapons" in statements[2]

    def test_semicolons_take_precedence_over_blank_lines(self):
        """Should use semicolons when present, ignoring blank lines."""
        from sqlit.domains.query.app.multi_statement import split_statements

        query = """SELECT * FROM vikings;

SELECT * FROM ships;
SELECT * FROM weapons"""
        statements = split_statements(query)

        assert len(statements) == 3
        # All three are split by semicolons, blank line is ignored

    def test_multiline_statement_stays_together(self):
        """Multi-line statement without blank lines should not be split."""
        from sqlit.domains.query.app.multi_statement import split_statements

        query = """SELECT v.name, s.name
FROM vikings v
JOIN ships s ON v.ship_id = s.id
WHERE v.active = true"""
        statements = split_statements(query)

        assert len(statements) == 1
        assert "JOIN" in statements[0]
        assert "WHERE" in statements[0]

    def test_blank_line_with_multiline_statements(self):
        """Should split by blank lines even with multi-line statements."""
        from sqlit.domains.query.app.multi_statement import split_statements

        query = """SELECT v.name
FROM vikings v
WHERE v.id = 1

SELECT s.name
FROM ships s
WHERE s.id = 2"""
        statements = split_statements(query)

        assert len(statements) == 2
        assert "vikings" in statements[0]
        assert "ships" in statements[1]

    def test_multiple_blank_lines_treated_as_one_separator(self):
        """Multiple consecutive blank lines should act as single separator."""
        from sqlit.domains.query.app.multi_statement import split_statements

        query = """SELECT 1


SELECT 2



SELECT 3"""
        statements = split_statements(query)

        assert len(statements) == 3

    def test_single_newline_does_not_split(self):
        """Single newline (no blank line) should not split."""
        from sqlit.domains.query.app.multi_statement import split_statements

        query = """SELECT *
FROM vikings"""
        statements = split_statements(query)

        assert len(statements) == 1

    def test_blank_line_with_whitespace_only(self):
        """Line with only whitespace should count as blank line."""
        from sqlit.domains.query.app.multi_statement import split_statements

        query = "SELECT 1\n   \nSELECT 2"
        statements = split_statements(query)

        assert len(statements) == 2

    def test_preserves_strings_with_newlines_in_blank_line_mode(self):
        """Should not split on blank lines inside string literals."""
        from sqlit.domains.query.app.multi_statement import split_statements

        query = """SELECT 'line1

line2' AS text

SELECT 'other'"""
        statements = split_statements(query)

        assert len(statements) == 2
        assert "line1" in statements[0]
        assert "line2" in statements[0]


class TestNormalizeSqlForExecution:
    """Tests for normalizing SQL before execution."""

    def test_adds_semicolons_between_blank_line_statements(self):
        """Blank-line-separated statements should be joined with semicolons for execution."""
        from sqlit.domains.query.app.multi_statement import normalize_for_execution

        query = """SELECT * FROM vikings

SELECT * FROM ships

SELECT * FROM weapons"""
        normalized = normalize_for_execution(query)

        # Should be semicolon-separated for database execution
        assert ";" in normalized
        # Should contain all three statements
        assert "vikings" in normalized
        assert "ships" in normalized
        assert "weapons" in normalized

    def test_preserves_semicolon_separated_statements(self):
        """Already semicolon-separated statements should stay as-is."""
        from sqlit.domains.query.app.multi_statement import normalize_for_execution

        query = "SELECT * FROM vikings; SELECT * FROM ships"
        normalized = normalize_for_execution(query)

        assert normalized == query

    def test_preserves_single_statement(self):
        """Single statement without semicolons should stay as-is."""
        from sqlit.domains.query.app.multi_statement import normalize_for_execution

        query = "SELECT * FROM vikings"
        normalized = normalize_for_execution(query)

        assert normalized == query

    def test_handles_multiline_single_statement(self):
        """Multi-line statement without blank lines should stay as-is."""
        from sqlit.domains.query.app.multi_statement import normalize_for_execution

        query = """SELECT *
FROM vikings
WHERE id = 1"""
        normalized = normalize_for_execution(query)

        assert normalized == query
        assert ";" not in normalized
