"""UI tests for the explorer toggle functionality."""

from __future__ import annotations

import pytest

from sqlit.domains.shell.app.main import SSMSTUI
from sqlit.domains.shell.ui.screens.leader_menu import LeaderMenuScreen
from sqlit.shared.ui.screens.confirm import ConfirmScreen

from .mocks import MockSettingsStore, build_test_services


def _make_app() -> SSMSTUI:
    services = build_test_services(settings_store=MockSettingsStore({"theme": "tokyo-night"}))
    return SSMSTUI(services=services)


class TestLeaderMenu:
    @pytest.mark.asyncio
    async def test_leader_menu_blocked_when_dialog_open(self):
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.push_screen(ConfirmScreen("Test dialog"))
            await pilot.pause()

            app._show_leader_menu()
            await pilot.pause()

            has_leader_menu = any(isinstance(screen, LeaderMenuScreen) for screen in app.screen_stack)
            assert not has_leader_menu


class TestExplorerToggle:
    """Test toggling the explorer sidebar visibility."""

    @pytest.mark.asyncio
    async def test_toggle_explorer_hides_sidebar(self):
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            assert app.sidebar.display is True

            app.action_toggle_explorer()
            await pilot.pause()

            assert app.sidebar.display is False

    @pytest.mark.asyncio
    async def test_hiding_explorer_moves_focus_to_query(self):
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_explorer()
            await pilot.pause()
            assert app.object_tree.has_focus

            app.action_toggle_explorer()
            await pilot.pause()

            assert app.query_input.has_focus


class TestFullscreen:
    """Test fullscreen toggle functionality."""

    @pytest.mark.asyncio
    async def test_explorer_fullscreen_hides_query_and_results(self):
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_explorer()
            await pilot.pause()

            app.action_toggle_fullscreen()
            await pilot.pause()

            assert app.main_panel.display is False

    @pytest.mark.asyncio
    async def test_query_fullscreen_hides_explorer_and_results(self):
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.action_toggle_fullscreen()
            await pilot.pause()

            assert app.sidebar.display is False
            assert app.results_area.display is False

    @pytest.mark.asyncio
    async def test_results_fullscreen_hides_explorer_and_query(self):
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            # Wait for Lazy widget to render the results table
            await pilot.pause()

            app.action_focus_results()
            await pilot.pause()

            app.action_toggle_fullscreen()
            await pilot.pause()

            assert app.sidebar.display is False
            assert app.query_area.display is False

    @pytest.mark.asyncio
    async def test_toggle_explorer_exits_query_fullscreen(self):
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.action_toggle_fullscreen()
            await pilot.pause()
            assert app.sidebar.display is False
            assert app.results_area.display is False

            app.action_toggle_explorer()
            await pilot.pause()

            assert app.sidebar.display is True
            assert app.results_area.display is True
