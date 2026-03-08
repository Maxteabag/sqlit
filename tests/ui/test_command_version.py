"""UI tests for :version command output."""

from __future__ import annotations

import pytest
from textual.coordinate import Coordinate

from sqlit import __version__
from sqlit.domains.shell.app.main import SSMSTUI

from .mocks import MockConnectionStore, MockSettingsStore, build_test_services


def _make_app() -> SSMSTUI:
    services = build_test_services(
        connection_store=MockConnectionStore(),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    return SSMSTUI(services=services)


class TestVersionCommand:
    """Test the :version command output."""

    @pytest.mark.asyncio
    async def test_version_command_updates_results_table(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            await pilot.pause()

            app._run_command("version")
            await pilot.pause()

            table = app.results_table
            assert table.row_count >= 1

            key = table.get_cell_at(Coordinate(0, 0))
            value = table.get_cell_at(Coordinate(0, 1))

            assert str(key) == "version"
            assert str(value) == __version__
