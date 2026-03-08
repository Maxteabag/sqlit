"""Unit test for incremental rendering with unsupported value types."""

from __future__ import annotations

import pytest

from decimal import Decimal

from sqlit.domains.shell.app.main import SSMSTUI

from tests.ui.mocks import MockConnectionStore, MockSettingsStore, build_test_services, create_test_connection


class NumericRange:
    def __init__(self, lower: int, upper: int, bounds: str = "[)") -> None:
        self.lower = lower
        self.upper = upper
        self.bounds = bounds

    def __str__(self) -> str:
        return f"NumericRange({self.lower}, {self.upper}, '{self.bounds}')"


@pytest.mark.asyncio
async def test_incremental_rendering_handles_numeric_range_values():
    """Incremental rendering should not crash on unsupported value types."""
    connections = [create_test_connection("test-db", "sqlite")]
    mock_connections = MockConnectionStore(connections)
    mock_settings = MockSettingsStore({"theme": "tokyo-night"})

    services = build_test_services(
        connection_store=mock_connections,
        settings_store=mock_settings,
    )
    app = SSMSTUI(services=services)

    columns = ["id", "amount", "range"]
    rows = [
        (i + 1, Decimal(f"{i + 1}.25"), NumericRange(i, i + 2))
        for i in range(201)
    ]

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
