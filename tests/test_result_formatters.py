"""Tests for sqlit.domains.results.formatters."""

from __future__ import annotations

import json

import pytest

from sqlit.domains.results.formatters import (
    FORMATS,
    format_csv,
    format_json,
    format_markdown,
    format_values_list,
)


COLS = ["id", "name", "note"]
ROWS: list[tuple] = [
    (1, "Alice", "a|b"),
    (2, "Bob", None),
    (3, "C\nD", "x"),
]


def test_csv_includes_header_and_handles_null():
    out = format_csv(COLS, ROWS)
    lines = out.strip().splitlines()
    assert lines[0] == "id,name,note"
    assert lines[2].endswith(",")  # NULL → empty string


def test_csv_empty_columns_skips_header():
    out = format_csv([], [(1, 2)])
    assert out.splitlines()[0] == "1,2"


def test_json_roundtrip():
    out = format_json(COLS, ROWS)
    parsed = json.loads(out)
    assert parsed[0]["name"] == "Alice"
    assert parsed[1]["note"] is None
    assert parsed[2]["name"] == "C\nD"


def test_markdown_table_header_separator_and_escapes():
    out = format_markdown(COLS, ROWS)
    lines = out.strip().splitlines()
    assert lines[0] == "| id | name | note |"
    assert lines[1] == "| --- | --- | --- |"
    # pipes escaped
    assert "a\\|b" in lines[2]
    # newline flattened
    assert "C D" in lines[4]
    # NULL renders as empty
    assert "| Bob |  |" in lines[3]


def test_markdown_empty_input():
    assert format_markdown([], []) == ""


def test_values_list_quotes_strings_and_passes_numbers():
    assert format_values_list([1, 2, 3]) == "1, 2, 3"
    assert format_values_list(["a", "b"]) == "'a', 'b'"


def test_values_list_escapes_single_quotes_and_handles_null_bool():
    assert format_values_list(["O'Brien", None, True, False]) == (
        "'O''Brien', NULL, TRUE, FALSE"
    )


def test_values_list_custom_separator():
    assert format_values_list([1, 2, 3], separator="; ") == "1; 2; 3"


def test_format_registry_keys_and_extensions():
    assert set(FORMATS) == {"csv", "json", "markdown"}
    assert FORMATS["markdown"].extension == "md"
    assert FORMATS["csv"].extension == "csv"
    assert FORMATS["json"].extension == "json"


@pytest.mark.parametrize("key", list(FORMATS))
def test_each_format_runs_on_sample(key):
    out = FORMATS[key].formatter(COLS, ROWS)
    assert isinstance(out, str) and out
