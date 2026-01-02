"""Tests for CLI command output functions."""

from __future__ import annotations

import io
import sys

from sqlit.domains.query.cli.commands import _output_table
from tests.ui.mocks import generate_long_varchar_rows


class TestOutputTableTruncation:
    """Tests for _output_table column truncation behavior."""

    def test_short_text_not_truncated(self):
        """Text under MAX_COL_WIDTH (50) should not be truncated."""
        columns = ["id", "short"]
        rows = [(1, "Hello World")]  # 11 chars, well under 50

        captured = io.StringIO()
        sys.stdout = captured
        try:
            _output_table(columns, rows, truncated=False)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()
        assert "Hello World" in output
        assert ".." not in output

    def test_long_text_truncated_with_dots(self):
        """Text over MAX_COL_WIDTH (50) should be truncated with '..'"""
        long_text = "A" * 100  # 100 chars, over 50 limit
        columns = ["id", "long_field"]
        rows = [(1, long_text)]

        captured = io.StringIO()
        sys.stdout = captured
        try:
            _output_table(columns, rows, truncated=False)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()
        # Should have truncation indicator
        assert ".." in output
        # Should NOT have the full 100-char string
        assert long_text not in output

    def test_text_at_limit_not_truncated(self):
        """Text exactly at MAX_COL_WIDTH (50) should not be truncated."""
        exact_text = "B" * 50  # Exactly 50 chars
        columns = ["id", "exact"]
        rows = [(1, exact_text)]

        captured = io.StringIO()
        sys.stdout = captured
        try:
            _output_table(columns, rows, truncated=False)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()
        assert exact_text in output
        assert ".." not in output

    def test_text_just_over_limit_truncated(self):
        """Text at 51 chars (just over limit) should be truncated."""
        over_text = "C" * 51
        columns = ["id", "over"]
        rows = [(1, over_text)]

        captured = io.StringIO()
        sys.stdout = captured
        try:
            _output_table(columns, rows, truncated=False)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()
        assert ".." in output
        assert over_text not in output

    def test_multiple_columns_mixed_lengths(self):
        """Multiple columns with varying lengths should truncate correctly."""
        cols, rows = generate_long_varchar_rows(row_count=2)

        captured = io.StringIO()
        sys.stdout = captured
        try:
            _output_table(cols, rows, truncated=False)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()
        # Columns over 50 chars should have truncation
        assert ".." in output
        # Row count should be shown
        assert "(2 row(s) returned)" in output

    def test_null_values_displayed(self):
        """NULL values should be displayed as 'NULL' string."""
        columns = ["id", "nullable"]
        rows = [(1, None), (2, "value")]

        captured = io.StringIO()
        sys.stdout = captured
        try:
            _output_table(columns, rows, truncated=False)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()
        assert "NULL" in output
        assert "value" in output

    def test_truncated_flag_shows_message(self):
        """When truncated=True, should show truncation message."""
        columns = ["id", "name"]
        rows = [(1, "Alice"), (2, "Bob")]

        captured = io.StringIO()
        sys.stdout = captured
        try:
            _output_table(columns, rows, truncated=True)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()
        assert "results truncated" in output

    def test_column_header_truncation(self):
        """Very long column names should also be truncated."""
        long_col_name = "this_is_a_very_long_column_name_that_exceeds_fifty_characters"
        columns = ["id", long_col_name]
        rows = [(1, "value")]

        captured = io.StringIO()
        sys.stdout = captured
        try:
            _output_table(columns, rows, truncated=False)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()
        # Full column name should not appear (it's 62 chars)
        assert long_col_name not in output


class TestGenerateLongVarcharRows:
    """Tests for the generate_long_varchar_rows helper itself."""

    def test_default_columns(self):
        """Default call should produce expected column structure."""
        cols, rows = generate_long_varchar_rows()

        assert cols[0] == "id"
        assert "short_text" in cols
        assert "very_long_text" in cols
        assert len(rows) == 5  # Default row count

    def test_custom_lengths(self):
        """Custom text lengths should be respected."""
        cols, rows = generate_long_varchar_rows(
            row_count=3,
            text_lengths={"tiny": 5, "huge": 500},
        )

        assert cols == ["id", "tiny", "huge"]
        assert len(rows) == 3

        # Check actual lengths
        for row in rows:
            assert len(row[1]) == 5    # tiny
            assert len(row[2]) == 500  # huge

    def test_predictable_pattern(self):
        """Generated text should have predictable pattern for verification."""
        cols, rows = generate_long_varchar_rows(row_count=2, text_lengths={"test": 20})

        # Row 1 should start with R1_, Row 2 with R2_
        assert rows[0][1].startswith("R1_")
        assert rows[1][1].startswith("R2_")
