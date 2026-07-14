"""Regression tests for process-worker statement validation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sqlit.domains.process_worker.app.process_worker import _WorkerState


def test_single_statement_with_trailing_comment_reaches_provider_lookup() -> None:
    """A trailing comment must not turn one query into two statements."""
    connection = MagicMock()
    state = _WorkerState(conn=connection)

    with patch.object(state, "_get_provider", return_value=None) as get_provider:
        state._start_query(
            {
                "id": 254,
                "query": "SELECT 1;\n-- trailing comment",
                "db_type": "sqlite",
                "config": {
                    "name": "issue-254",
                    "db_type": "sqlite",
                    "file_path": ":memory:",
                },
            }
        )

    rejection = next(
        (
            call.args[0]
            for call in connection.send.call_args_list
            if call.args[0].get("message")
            == "Multi-statement queries are not supported in the process worker."
        ),
        None,
    )
    assert rejection is None, rejection["message"] if rejection else ""
    get_provider.assert_called_once_with("sqlite")


def test_multiple_executable_statements_are_rejected() -> None:
    """The comment fix must not allow genuine multi-statement queries."""
    connection = MagicMock()
    state = _WorkerState(conn=connection)

    with patch.object(state, "_get_provider") as get_provider:
        state._start_query(
            {
                "id": 255,
                "query": "SELECT 1; SELECT 2",
                "db_type": "sqlite",
                "config": {
                    "name": "multi-statement",
                    "db_type": "sqlite",
                    "file_path": ":memory:",
                },
            }
        )

    get_provider.assert_not_called()
    connection.send.assert_called_once_with(
        {
            "type": "error",
            "id": 255,
            "message": "Multi-statement queries are not supported in the process worker.",
        }
    )
