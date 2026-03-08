"""UI tests for multi-select connection actions."""

from __future__ import annotations

import pytest

from sqlit.domains.connections.ui.screens import FolderInputScreen
from sqlit.domains.shell.app.main import SSMSTUI
from sqlit.shared.ui.screens.confirm import ConfirmScreen

from .mocks import MockConnectionStore, MockSettingsStore, build_test_services, create_test_connection


def _make_app(connections: list) -> SSMSTUI:
    mock_connections = MockConnectionStore(connections)
    services = build_test_services(
        connection_store=mock_connections,
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    return SSMSTUI(services=services)


class TestMultiSelectActions:
    @pytest.mark.asyncio
    async def test_move_clears_selection(self):
        connections = [
            create_test_connection("Alpha", "sqlite"),
            create_test_connection("Bravo", "sqlite"),
        ]
        app = _make_app(connections)

        async with app.run_test(size=(100, 35)) as pilot:
            await pilot.pause()
            app._selected_connection_names = {"Alpha", "Bravo"}

            app.action_move_connection_to_folder()
            await pilot.pause()

            screen = next(
                (s for s in app.screen_stack if isinstance(s, FolderInputScreen)),
                None,
            )
            assert screen is not None
            screen.dismiss("Team/Prod")
            await pilot.pause()

            assert not app._selected_connection_names

    @pytest.mark.asyncio
    async def test_delete_clears_selection(self):
        connections = [
            create_test_connection("Alpha", "sqlite"),
            create_test_connection("Bravo", "sqlite"),
        ]
        app = _make_app(connections)

        async with app.run_test(size=(100, 35)) as pilot:
            await pilot.pause()
            app._selected_connection_names = {"Alpha", "Bravo"}

            app.action_delete_connection()
            await pilot.pause()

            screen = next(
                (s for s in app.screen_stack if isinstance(s, ConfirmScreen)),
                None,
            )
            assert screen is not None
            screen.action_yes()
            await pilot.pause()

            assert not app._selected_connection_names
