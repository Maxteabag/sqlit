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
    project_columns,
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


def test_project_columns_subset():
    cols, rows = project_columns(COLS, ROWS, [0, 2])
    assert cols == ["id", "note"]
    assert rows == [(1, "a|b"), (2, None), (3, "x")]


def test_project_columns_reorders_to_given_indices_sorted():
    # The action layer passes already-sorted indices; project_columns honors order.
    cols, rows = project_columns(COLS, ROWS, [2, 0])
    assert cols == ["note", "id"]
    assert rows[0] == ("a|b", 1)


def test_project_columns_ignores_out_of_range():
    cols, _rows = project_columns(COLS, ROWS, [0, 99])
    assert cols == ["id"]


def test_project_columns_empty_indices_yields_empty_rows():
    cols, rows = project_columns(COLS, ROWS, [])
    assert cols == []
    assert rows == [(), (), ()]


def test_project_columns_composes_with_csv():
    cols, rows = project_columns(COLS, ROWS, [1])
    out = format_csv(cols, rows)
    # csv.writer quotes embedded newlines so the multi-line cell stays intact.
    assert out.startswith("name\r\nAlice\r\nBob\r\n")
    assert '"C\nD"' in out
