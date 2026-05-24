"""Regression tests for process worker pickle safety (issue #161 follow-up).

Two layers of defence:

1. `CursorBasedAdapter.execute_query` sanitizes rows before returning, so
   `memoryview` (from psycopg2 bytea) becomes `bytes`. This is what PR #171
   landed. We pin that wiring here with a mock cursor, and check the
   sanitized output is picklable.

2. `_WorkerState.send` surfaces a pickle failure as an error message
   instead of silently dropping it — otherwise the client's `recv()`
   waits forever. Without this, any non-picklable cell type (not just
   bytea) would still hang the TUI.
"""

from __future__ import annotations

import multiprocessing
import pickle
from multiprocessing.connection import Connection
from typing import Any

from sqlit.domains.connections.providers.adapters.base import (
    CursorBasedAdapter,
    _sanitize_row,
)
from sqlit.domains.process_worker.app.process_worker import _WorkerState


class _FakeCursor:
    """Minimal stand-in for a DB-API cursor."""

    def __init__(self, columns: list[str], rows: list[tuple]) -> None:
        self.description = [(name,) for name in columns]
        self._rows = list(rows)

    def execute(self, sql: str) -> None:  # noqa: ARG002
        pass

    def fetchall(self) -> list[tuple]:
        return self._rows

    def fetchmany(self, size: int) -> list[tuple]:
        head, self._rows = self._rows[:size], self._rows[size:]
        return head


class _FakeConn:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _FakeCursor:
        return self._cursor


def test_execute_query_sanitizes_memoryview_in_returned_rows() -> None:
    """Pins the `_sanitize_row` call in CursorBasedAdapter.execute_query.

    Without the call site wiring, this test fails even if _sanitize_row
    itself is correct.
    """
    # CursorBasedAdapter is abstract but execute_query doesn't touch self,
    # so call it unbound.
    cursor = _FakeCursor(
        columns=["id", "blob"],
        rows=[(1, memoryview(b"\xde\xad\xbe\xef"))],
    )
    columns, rows, truncated = CursorBasedAdapter.execute_query(
        None,  # type: ignore[arg-type]
        _FakeConn(cursor),
        "SELECT 1",
    )

    assert columns == ["id", "blob"]
    assert truncated is False
    assert rows == [(1, b"\xde\xad\xbe\xef")]
    assert isinstance(rows[0][1], bytes)


def test_sanitized_rows_are_picklable() -> None:
    """The actual failure mode in #161 was pickle failing on memoryview.

    Pickle round-trip is the closest cheap stand-in for `Pipe.send()`,
    which is what hung the worker.
    """
    raw = [(1, "row1", memoryview(b"\xca\xfe\xba\xbe"))]
    sanitized = [_sanitize_row(r) for r in raw]

    data = pickle.dumps(sanitized)
    assert pickle.loads(data) == [(1, "row1", b"\xca\xfe\xba\xbe")]


def _make_state_with_pipe() -> tuple[_WorkerState, Connection]:
    """Build a _WorkerState attached to a real in-process pipe."""
    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe(duplex=True)
    state = _WorkerState(conn=child)
    return state, parent


def test_worker_send_non_picklable_payload_emits_error() -> None:
    """Defence-in-depth: if a future driver returns something non-picklable,
    the client should receive an error message, not hang on recv().
    """
    state, parent = _make_state_with_pipe()
    try:
        # memoryview is not picklable — simulates any unexpected non-picklable cell.
        payload: dict[str, Any] = {
            "type": "result",
            "id": 42,
            "kind": "query",
            "result": memoryview(b"not picklable"),
        }
        state.send(payload)

        assert parent.poll(timeout=2.0), "client would hang; no error message was sent"
        message = parent.recv()
        assert message["type"] == "error"
        assert message["id"] == 42
        assert "could not be serialized" in message["message"].lower()
    finally:
        parent.close()
        state.conn.close()


def test_worker_send_picklable_payload_passes_through() -> None:
    """Confirm the fallback path doesn't interfere with normal sends."""
    state, parent = _make_state_with_pipe()
    try:
        payload = {"type": "result", "id": 1, "kind": "query", "result": [1, 2, 3]}
        state.send(payload)

        assert parent.poll(timeout=2.0)
        message = parent.recv()
        assert message == payload
    finally:
        parent.close()
        state.conn.close()
