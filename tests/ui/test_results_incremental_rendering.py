"""UI tests for incremental results rendering edge cases."""

from __future__ import annotations

from decimal import Decimal
from types import MethodType

import pytest

from sqlit.domains.shell.app.main import SSMSTUI

from .mocks import MockConnectionStore, MockSettingsStore, build_test_services, create_test_connection


@pytest.mark.asyncio
async def test_incremental_rendering_decimal_scale_mismatch():
    """Incremental rendering should not drop rows when Decimal scale changes mid-stream."""
    connections = [create_test_connection("test-db", "sqlite")]
    mock_connections = MockConnectionStore(connections)
    mock_settings = MockSettingsStore({"theme": "tokyo-night"})

    services = build_test_services(
        connection_store=mock_connections,
        settings_store=mock_settings,
    )
    app = SSMSTUI(services=services)

    columns = ["id", "amount"]
    rows: list[tuple[int, Decimal]] = []
    for i in range(201):
        if i < 20:
            rows.append((i + 1, Decimal(i + 1)))
        else:
            rows.append((i + 1, Decimal(f"{i + 1}.25")))

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        fallback_called = {"value": False}

        original_replace = app._replace_results_table_with_data

        def _wrapped_replace(self, columns, rows, *, escape):
            fallback_called["value"] = True
            return original_replace(columns, rows, escape=escape)

        app._replace_results_table_with_data = MethodType(_wrapped_replace, app)

        await app._display_query_results(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=False,
            elapsed_ms=0,
        )

        # Allow incremental render timers to run.
        for _ in range(3):
            await pilot.pause(0.05)

        assert app.results_table.row_count == len(rows)
        assert fallback_called["value"] is False


@pytest.mark.asyncio
async def test_incremental_rendering_skips_decimal_scan_without_initial_decimal():
    """Decimal scan should be skipped when initial rows contain no Decimal."""
    connections = [create_test_connection("test-db", "sqlite")]
    mock_connections = MockConnectionStore(connections)
    mock_settings = MockSettingsStore({"theme": "tokyo-night"})

    services = build_test_services(
        connection_store=mock_connections,
        settings_store=mock_settings,
    )
    app = SSMSTUI(services=services)

    columns = ["id", "amount"]
    rows = [(i + 1, i + 1) for i in range(201)]

    def _unexpected_decimal_scan(*_args, **_kwargs):
        raise AssertionError("Decimal scan should not run for non-decimal initial rows")

    app._get_decimal_column_types = MethodType(_unexpected_decimal_scan, app)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        await app._display_query_results(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=False,
            elapsed_ms=0,
        )

        for _ in range(3):
            await pilot.pause(0.05)

        assert app.results_table.row_count == len(rows)


@pytest.mark.asyncio
async def test_incremental_rendering_fallback_on_append_error(monkeypatch):
    """Fallback should trigger when incremental append fails."""
    from sqlit.shared.ui.widgets_tables import SqlitDataTable

    connections = [create_test_connection("test-db", "sqlite")]
    mock_connections = MockConnectionStore(connections)
    mock_settings = MockSettingsStore({"theme": "tokyo-night"})

    services = build_test_services(
        connection_store=mock_connections,
        settings_store=mock_settings,
    )
    app = SSMSTUI(services=services)

    columns = ["id", "amount"]
    rows = [(i + 1, Decimal(f"{i + 1}.25")) for i in range(201)]

    original_add_rows = SqlitDataTable.add_rows

    def _failing_add_rows(self, _rows):
        raise RuntimeError("forced append failure")

    monkeypatch.setattr(SqlitDataTable, "add_rows", _failing_add_rows)

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        fallback_called = {"value": False}
        original_replace = app._replace_results_table_with_data

        def _wrapped_replace(self, columns, rows, *, escape):
            fallback_called["value"] = True
            return original_replace(columns, rows, escape=escape)

        app._replace_results_table_with_data = MethodType(_wrapped_replace, app)

        await app._display_query_results(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=False,
            elapsed_ms=0,
        )

        for _ in range(3):
            await pilot.pause(0.05)

        assert app.results_table.row_count == len(rows)
        assert fallback_called["value"] is True

    monkeypatch.setattr(SqlitDataTable, "add_rows", original_add_rows)


class _WeirdType:
    def __init__(self, value: str) -> None:
        self.value = value

    def __str__(self) -> str:
        return f"Weird({self.value})"


@pytest.mark.asyncio
async def test_incremental_rendering_coerces_unsupported_initial_types():
    """Unsupported types in initial rows should be coerced without forcing fallback."""
    connections = [create_test_connection("test-db", "sqlite")]
    mock_connections = MockConnectionStore(connections)
    mock_settings = MockSettingsStore({"theme": "tokyo-night"})

    services = build_test_services(
        connection_store=mock_connections,
        settings_store=mock_settings,
    )
    app = SSMSTUI(services=services)

    columns = ["id", "amount", "range"]
    rows = []
    for i in range(201):
        rows.append((i + 1, Decimal(f"{i + 1}.25"), _WeirdType(str(i))))

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()

        fallback_called = {"value": False}
        original_replace = app._replace_results_table_with_data

        def _wrapped_replace(self, columns, rows, *, escape):
            fallback_called["value"] = True
            return original_replace(columns, rows, escape=escape)

        app._replace_results_table_with_data = MethodType(_wrapped_replace, app)

        await app._display_query_results(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=False,
            elapsed_ms=0,
        )

        for _ in range(3):
            await pilot.pause(0.05)

        assert app.results_table.row_count == len(rows)
        assert fallback_called["value"] is False
