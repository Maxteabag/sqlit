"""SQL Server splits FOR JSON / FOR XML output over many rows; sqlit shows one document (#336)."""

from __future__ import annotations

import json

from sqlit.domains.connections.providers.mssql.adapter import SQLServerAdapter

FOR_JSON_COLUMN = "JSON_F52E2B61-18A1-11d1-B105-00805F49916B"


class _Cursor:
    def __init__(self, column: str, rows: list[tuple]):
        self.description = [(column, None, None, None, None, None, None)]
        self._rows = rows

    def execute(self, query):
        pass

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows

    def fetchmany(self, n):
        rows, self._rows = self._rows[:n], self._rows[n:]
        return rows


class _Conn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def _chunks(document: str, size: int = 2033) -> list[tuple]:
    return [(document[i : i + size],) for i in range(0, len(document), size)]


def test_for_json_chunks_become_one_valid_document_even_past_the_row_limit():
    document = json.dumps([{"id": i, "name": f"Customer {i}"} for i in range(500)], separators=(",", ":"))
    conn = _Conn(_Cursor(FOR_JSON_COLUMN, _chunks(document)))

    columns, rows, truncated = SQLServerAdapter().execute_query(conn, "SELECT * FROM t FOR JSON PATH", max_rows=3)

    assert columns == [FOR_JSON_COLUMN]
    assert rows == [(document,)]
    assert truncated is False
    assert len(json.loads(rows[0][0])) == 500


def test_ordinary_single_column_results_are_untouched():
    conn = _Conn(_Cursor(FOR_JSON_COLUMN + "_label", [("a",), ("b",), ("c",)]))

    columns, rows, truncated = SQLServerAdapter().execute_query(conn, "SELECT name FROM t", max_rows=2)

    assert rows == [("a",), ("b",)]
    assert truncated is True
