"""Tests for charset handling across database providers.

These tests verify that sqlit correctly handles databases configured with
legacy character sets like TIS-620 (Thai) and Latin1.
"""

from __future__ import annotations

import json

import pytest

from tests.fixtures.utils import run_cli


class TestMySQLTIS620Charset:
    """Test Thai TIS-620 charset support in MySQL."""

    def test_thai_characters_read_correctly(self, mysql_tis620_connection: str) -> None:
        """Test reading Thai data from TIS-620 MySQL database.

        This test verifies that Thai characters stored in a TIS-620 encoded
        database are correctly read and displayed without garbling.
        """
        result = run_cli(
            "query",
            "-c",
            mysql_tis620_connection,
            "-q",
            "SELECT content FROM charset_test WHERE id = 1",
            "--format",
            "json",
            check=False,
        )

        assert result.returncode == 0, f"Query failed: {result.stderr}"
        data = json.loads(result.stdout)

        # The key assertion: Thai text should not be garbled
        expected = "สวัสดีครับ"
        actual = data[0]["content"]

        assert actual == expected, (
            f"Thai charset mismatch!\n"
            f"Expected: {expected}\n"
            f"Got: {actual}\n"
            f"This indicates charset auto-detection is not working."
        )

    def test_thai_language_name(self, mysql_tis620_connection: str) -> None:
        """Test reading 'Thai language' in Thai script."""
        result = run_cli(
            "query",
            "-c",
            mysql_tis620_connection,
            "-q",
            "SELECT content FROM charset_test WHERE id = 2",
            "--format",
            "json",
            check=False,
        )

        assert result.returncode == 0, f"Query failed: {result.stderr}"
        data = json.loads(result.stdout)

        expected = "ภาษาไทย"
        actual = data[0]["content"]

        assert actual == expected, f"Expected: {expected}, Got: {actual}"

    def test_bangkok_city_name(self, mysql_tis620_connection: str) -> None:
        """Test reading Bangkok city name in Thai script."""
        result = run_cli(
            "query",
            "-c",
            mysql_tis620_connection,
            "-q",
            "SELECT content FROM charset_test WHERE id = 3",
            "--format",
            "json",
            check=False,
        )

        assert result.returncode == 0, f"Query failed: {result.stderr}"
        data = json.loads(result.stdout)

        expected = "กรุงเทพมหานคร"
        actual = data[0]["content"]

        assert actual == expected, f"Expected: {expected}, Got: {actual}"

    def test_all_thai_rows(self, mysql_tis620_connection: str) -> None:
        """Test reading all Thai rows in a single query."""
        result = run_cli(
            "query",
            "-c",
            mysql_tis620_connection,
            "-q",
            "SELECT id, content FROM charset_test ORDER BY id",
            "--format",
            "json",
            check=False,
        )

        assert result.returncode == 0, f"Query failed: {result.stderr}"
        data = json.loads(result.stdout)

        expected_values = {
            1: "สวัสดีครับ",
            2: "ภาษาไทย",
            3: "กรุงเทพมหานคร",
        }

        assert len(data) == 3, f"Expected 3 rows, got {len(data)}"

        for row in data:
            row_id = row["id"]
            expected = expected_values[row_id]
            actual = row["content"]
            assert actual == expected, (
                f"Row {row_id}: Expected '{expected}', Got '{actual}'"
            )


class TestMySQLLatin1Charset:
    """Test Latin1 charset support in MySQL."""

    def test_french_accents(self, mysql_latin1_connection: str) -> None:
        """Test reading French accented characters from Latin1 database."""
        result = run_cli(
            "query",
            "-c",
            mysql_latin1_connection,
            "-q",
            "SELECT content FROM charset_test WHERE id = 1",
            "--format",
            "json",
            check=False,
        )

        assert result.returncode == 0, f"Query failed: {result.stderr}"
        data = json.loads(result.stdout)

        expected = "café"
        actual = data[0]["content"]

        assert actual == expected, f"Expected: {expected}, Got: {actual}"

    def test_french_diaeresis(self, mysql_latin1_connection: str) -> None:
        """Test reading French word with diaeresis from Latin1 database."""
        result = run_cli(
            "query",
            "-c",
            mysql_latin1_connection,
            "-q",
            "SELECT content FROM charset_test WHERE id = 2",
            "--format",
            "json",
            check=False,
        )

        assert result.returncode == 0, f"Query failed: {result.stderr}"
        data = json.loads(result.stdout)

        expected = "naïve"
        actual = data[0]["content"]

        assert actual == expected, f"Expected: {expected}, Got: {actual}"

    def test_german_umlaut(self, mysql_latin1_connection: str) -> None:
        """Test reading German name with umlaut from Latin1 database."""
        result = run_cli(
            "query",
            "-c",
            mysql_latin1_connection,
            "-q",
            "SELECT content FROM charset_test WHERE id = 3",
            "--format",
            "json",
            check=False,
        )

        assert result.returncode == 0, f"Query failed: {result.stderr}"
        data = json.loads(result.stdout)

        expected = "Müller"
        actual = data[0]["content"]

        assert actual == expected, f"Expected: {expected}, Got: {actual}"

    def test_spanish_tilde(self, mysql_latin1_connection: str) -> None:
        """Test reading Spanish word with tilde from Latin1 database."""
        result = run_cli(
            "query",
            "-c",
            mysql_latin1_connection,
            "-q",
            "SELECT content FROM charset_test WHERE id = 4",
            "--format",
            "json",
            check=False,
        )

        assert result.returncode == 0, f"Query failed: {result.stderr}"
        data = json.loads(result.stdout)

        expected = "señor"
        actual = data[0]["content"]

        assert actual == expected, f"Expected: {expected}, Got: {actual}"

    def test_all_latin1_rows(self, mysql_latin1_connection: str) -> None:
        """Test reading all Latin1 rows in a single query."""
        result = run_cli(
            "query",
            "-c",
            mysql_latin1_connection,
            "-q",
            "SELECT id, content FROM charset_test ORDER BY id",
            "--format",
            "json",
            check=False,
        )

        assert result.returncode == 0, f"Query failed: {result.stderr}"
        data = json.loads(result.stdout)

        expected_values = {
            1: "café",
            2: "naïve",
            3: "Müller",
            4: "señor",
        }

        assert len(data) == 4, f"Expected 4 rows, got {len(data)}"

        for row in data:
            row_id = row["id"]
            expected = expected_values[row_id]
            actual = row["content"]
            assert actual == expected, (
                f"Row {row_id}: Expected '{expected}', Got '{actual}'"
            )


class TestMySQLUTF8Baseline:
    """Baseline tests: UTF-8 MySQL should always work correctly."""

    def test_unicode_insert_and_read(self, mysql_connection: str) -> None:
        """Test that UTF-8 MySQL handles Unicode correctly (baseline)."""
        import uuid

        # Use a unique table name to avoid conflicts
        table_name = f"unicode_test_{uuid.uuid4().hex[:8]}"

        try:
            # Create a real table (not TEMPORARY since each CLI call is a separate connection)
            create_result = run_cli(
                "query",
                "-c",
                mysql_connection,
                "-q",
                f"CREATE TABLE {table_name} (id INT, content TEXT)",
                check=False,
            )
            assert create_result.returncode == 0, f"Create failed: {create_result.stderr}"

            # Insert various Unicode characters
            insert_result = run_cli(
                "query",
                "-c",
                mysql_connection,
                "-q",
                f"INSERT INTO {table_name} VALUES (1, 'Hello'), (2, 'café'), (3, 'สวัสดี'), (4, '你好')",
                check=False,
            )
            assert insert_result.returncode == 0, f"Insert failed: {insert_result.stderr}"

            # Read back and verify
            result = run_cli(
                "query",
                "-c",
                mysql_connection,
                "-q",
                f"SELECT id, content FROM {table_name} ORDER BY id",
                "--format",
                "json",
                check=False,
            )

            assert result.returncode == 0, f"Query failed: {result.stderr}"
            data = json.loads(result.stdout)

            expected_values = {
                1: "Hello",
                2: "café",
                3: "สวัสดี",
                4: "你好",
            }

            for row in data:
                row_id = row["id"]
                expected = expected_values[row_id]
                actual = row["content"]
                assert actual == expected, (
                    f"UTF-8 baseline failed! Row {row_id}: Expected '{expected}', Got '{actual}'"
                )
        finally:
            # Cleanup the table
            run_cli(
                "query",
                "-c",
                mysql_connection,
                "-q",
                f"DROP TABLE IF EXISTS {table_name}",
                check=False,
            )
