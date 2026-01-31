"""Tests for auto-refreshing explorer after schema-changing queries."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sqlit.domains.query.app.query_service import NonQueryResult, QueryResult
from sqlit.domains.query.ui.mixins.query_execution import QueryExecutionMixin


class MockExecutor:
    def __init__(self, result) -> None:
        self._result = result

    def execute(self, query: str, max_rows: int | None = None):
        _ = query, max_rows
        return self._result


class MockHost(QueryExecutionMixin):
    def __init__(self) -> None:
        self.current_connection = object()
        self.current_provider = MagicMock()
        self.current_provider.apply_database_override = lambda config, db: config
        self.current_provider.metadata = MagicMock(db_type="mock")
        self.current_config = MagicMock()
        self.current_config.tcp_endpoint = MagicMock(database="")
        self.query_input = MagicMock()
        self.services = MagicMock()
        self.services.runtime.max_rows = 100
        self.services.runtime.query_alert_mode = 0
        self._query_worker = None
        self._query_spinner = None
        self._query_target_database = None
        self._executor = MockExecutor(NonQueryResult(rows_affected=0))
        self._refresh_called = False

    def _use_process_worker(self, provider) -> bool:
        _ = provider
        return False

    def _get_transaction_executor(self, config, provider):
        _ = config, provider
        return self._executor

    async def _display_query_results(self, columns, rows, row_count, truncated, elapsed_ms) -> None:
        _ = columns, rows, row_count, truncated, elapsed_ms

    def _display_non_query_result(self, affected, elapsed_ms) -> None:
        _ = affected, elapsed_ms

    def _display_multi_statement_results(self, multi_result, elapsed_ms) -> None:
        _ = multi_result, elapsed_ms

    def _display_query_error(self, error_message: str) -> None:
        _ = error_message

    def _stop_query_spinner(self) -> None:
        pass

    def _get_effective_database(self):
        return None

    def call_after_refresh(self, callback) -> None:
        callback()

    def _refresh_tree_after_query(self) -> None:
        self._refresh_called = True


@pytest.mark.asyncio
async def test_schema_change_query_triggers_refresh() -> None:
    host = MockHost()
    await host._run_query_async("CREATE TABLE test_users(id INT)", keep_insert_mode=False)
    assert host._refresh_called is True


@pytest.mark.asyncio
async def test_select_query_does_not_trigger_refresh() -> None:
    host = MockHost()
    host._executor = MockExecutor(QueryResult(columns=[], rows=[], row_count=0, truncated=False))
    await host._run_query_async("SELECT * FROM test_users", keep_insert_mode=False)
    assert host._refresh_called is False
