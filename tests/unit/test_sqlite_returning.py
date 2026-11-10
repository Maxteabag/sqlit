"""Regression tests for issue #147: SQLite UPDATE ... RETURNING crashes on commit."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from sqlit.domains.connections.providers.sqlite.adapter import SQLiteAdapter
from sqlit.domains.query.app.query_service import DialectQueryAnalyzer, KeywordQueryAnalyzer, QueryKind
from sqlit.domains.query.cli.commands import _should_stream_results


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


def test_classifier_recognizes_update_returning_as_returns_rows():
    """`UPDATE ... RETURNING` produces a result set, so the analyzer must classify it as RETURNS_ROWS."""
    analyzer = KeywordQueryAnalyzer()
    sql = "UPDATE jobs SET status = status WHERE id = 1 RETURNING id"
    assert analyzer.classify(sql) == QueryKind.RETURNS_ROWS


def test_classifier_recognizes_insert_returning_as_returns_rows():
    analyzer = KeywordQueryAnalyzer()
    sql = "INSERT INTO jobs (id, status) VALUES (3, 'new') RETURNING id"
    assert analyzer.classify(sql) == QueryKind.RETURNS_ROWS


def test_classifier_recognizes_delete_returning_as_returns_rows():
    analyzer = KeywordQueryAnalyzer()
    sql = "DELETE FROM jobs WHERE id = 1 RETURNING id"
    assert analyzer.classify(sql) == QueryKind.RETURNS_ROWS


def test_dialect_classifier_recognizes_returning():
    """The analyzer real queries go through asks the adapter, not the keyword fallback."""
    analyzer = DialectQueryAnalyzer(SQLiteAdapter())
    assert analyzer.classify("UPDATE jobs SET status = 'x' RETURNING id") == QueryKind.RETURNS_ROWS
    assert analyzer.classify("UPDATE jobs SET status = 'x'") == QueryKind.NON_QUERY


def test_cli_does_not_stream_dml_returning():
    """Streaming skips the commit, so a write must take the normal path."""
    analyzer = DialectQueryAnalyzer(SQLiteAdapter())
    kwargs = {"max_rows": None, "fmt": "json", "analyzer": analyzer, "has_cursor": True}
    assert not _should_stream_results(query="UPDATE jobs SET status = 'x' RETURNING id", **kwargs)
    assert _should_stream_results(query="SELECT id FROM jobs", **kwargs)


def test_classifier_plain_update_is_non_query():
    """Plain DML without RETURNING must still be NON_QUERY (sanity check we don't over-correct)."""
    analyzer = KeywordQueryAnalyzer()
    assert analyzer.classify("UPDATE jobs SET status = 'done'") == QueryKind.NON_QUERY


def test_sqlite_execute_query_runs_update_returning_and_persists(jobs_db: Path):
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
