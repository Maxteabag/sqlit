"""Regression tests for issue #147: SQLite UPDATE ... RETURNING crashes on commit."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from sqlit.domains.connections.providers.sqlite.adapter import SQLiteAdapter
from sqlit.domains.query.app.query_service import KeywordQueryAnalyzer, QueryKind


@pytest.fixture
def jobs_db(tmp_path: Path) -> Path:
    """A tiny SQLite DB with a `jobs` table for RETURNING tests."""
    db = tmp_path / "jobs.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY, status TEXT)")
    conn.executemany("INSERT INTO jobs (id, status) VALUES (?, ?)", [(1, "new"), (2, "new")])
    conn.commit()
    conn.close()
    return db


def test_classifier_recognizes_update_returning_as_returns_rows() -> None:
    """`UPDATE ... RETURNING` produces a result set, so the analyzer must classify it as RETURNS_ROWS."""
    analyzer = KeywordQueryAnalyzer()
    sql = "UPDATE jobs SET status = status WHERE id = 1 RETURNING id"
    assert analyzer.classify(sql) == QueryKind.RETURNS_ROWS


def test_classifier_recognizes_insert_returning_as_returns_rows() -> None:
    analyzer = KeywordQueryAnalyzer()
    sql = "INSERT INTO jobs (id, status) VALUES (3, 'new') RETURNING id"
    assert analyzer.classify(sql) == QueryKind.RETURNS_ROWS


def test_classifier_recognizes_delete_returning_as_returns_rows() -> None:
    analyzer = KeywordQueryAnalyzer()
    sql = "DELETE FROM jobs WHERE id = 1 RETURNING id"
    assert analyzer.classify(sql) == QueryKind.RETURNS_ROWS


def test_classifier_plain_update_is_non_query() -> None:
    """Plain DML without RETURNING must still be NON_QUERY (sanity check we don't over-correct)."""
    analyzer = KeywordQueryAnalyzer()
    assert analyzer.classify("UPDATE jobs SET status = 'done'") == QueryKind.NON_QUERY


def test_classifier_recognizes_call_as_returns_rows() -> None:
    analyzer = KeywordQueryAnalyzer()
    assert analyzer.classify("CALL getalltheme()") == QueryKind.RETURNS_ROWS


def test_classifier_recognizes_exec_as_returns_rows() -> None:
    analyzer = KeywordQueryAnalyzer()
    assert analyzer.classify("EXEC getalltheme") == QueryKind.RETURNS_ROWS


def test_classifier_recognizes_execute_as_returns_rows() -> None:
    analyzer = KeywordQueryAnalyzer()
    assert analyzer.classify("EXECUTE getalltheme") == QueryKind.RETURNS_ROWS


def test_sqlite_execute_query_runs_update_returning_and_persists(jobs_db: Path) -> None:
    """UPDATE ... RETURNING via execute_query must return the row AND persist the change."""
    adapter = SQLiteAdapter()
    conn = sqlite3.connect(str(jobs_db))
    try:
        columns, rows, _ = adapter.execute_query(
            conn,
            "UPDATE jobs SET status = 'done' WHERE id = 1 RETURNING id, status",
        )
        assert columns == ["id", "status"]
        assert rows == [(1, "done")]
    finally:
        conn.close()

    # Verify the write was actually committed by opening a fresh connection.
    verify = sqlite3.connect(str(jobs_db))
    try:
        result = verify.execute("SELECT status FROM jobs WHERE id = 1").fetchone()
        assert result == ("done",), f"UPDATE ... RETURNING did not persist; got {result!r}"
    finally:
        verify.close()
