"""UI tests for autocomplete close behavior."""

from __future__ import annotations

import pytest

from sqlit.core.vim import VimMode
from sqlit.domains.shell.app.main import SSMSTUI

from .mocks import MockConnectionStore, MockSettingsStore, build_test_services


def _make_app() -> SSMSTUI:
    services = build_test_services(
        connection_store=MockConnectionStore(),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    return SSMSTUI(services=services)


class TestAutocompleteClose:
    """Autocomplete should close when leaving INSERT mode."""

    @pytest.mark.asyncio
    async def test_escape_closes_autocomplete_and_exits_insert(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "sel"
            app.query_input.cursor_location = (0, 3)
            await pilot.pause()

            # Enter INSERT mode
            await pilot.press("i")
            await pilot.pause()
            assert app.vim_mode == VimMode.INSERT
            assert app.query_input.read_only is False

            # Open autocomplete manually (simulating suggestions)
            app._show_autocomplete(["select", "set"], "sel")
            await pilot.pause()
            assert app._autocomplete_visible is True

            # Press Escape to leave INSERT mode
            await pilot.press("escape")
            await pilot.pause()

            assert app.vim_mode == VimMode.NORMAL
            assert app._autocomplete_visible is False
            assert app.query_input.read_only is True

    @pytest.mark.asyncio
    async def test_escape_closes_autocomplete_from_normal_mode(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "sel"
            await pilot.pause()
            assert app.vim_mode == VimMode.NORMAL

            # Open autocomplete while in normal mode (edge case)
            app._show_autocomplete(["select", "set"], "sel")
            await pilot.pause()
            assert app._autocomplete_visible is True

            await pilot.press("escape")
            await pilot.pause()

            assert app.vim_mode == VimMode.NORMAL
            assert app._autocomplete_visible is False
