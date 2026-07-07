"""UI tests for Tab behavior in the query editor."""

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


class TestQueryTabInsertion:
    """Tab should insert a real tab character in INSERT mode."""

    @pytest.mark.asyncio
    async def test_tab_inserts_tab_character_in_insert_mode(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "select"
            app.query_input.cursor_location = (0, 6)
            await pilot.pause()

            await pilot.press("i")
            await pilot.pause()
            assert app.vim_mode == VimMode.INSERT

            await pilot.press("tab")
            await pilot.pause()

            assert app.query_input.text == "select\t"
            assert "\t" in app.query_input.text

    @pytest.mark.asyncio
    async def test_tab_accepts_autocomplete_suggestion(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "sel"
            app.query_input.cursor_location = (0, 3)
            await pilot.pause()

            await pilot.press("i")
            await pilot.pause()
            assert app.vim_mode == VimMode.INSERT

            # Open autocomplete manually with "select" as first suggestion
            app._show_autocomplete(["select", "set"], "sel")
            await pilot.pause()
            assert app._autocomplete_visible is True

            await pilot.press("tab")
            await pilot.pause()

            assert app._autocomplete_visible is False
            assert app.query_input.text == "select"

    @pytest.mark.asyncio
    async def test_tab_does_not_insert_in_normal_mode(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.pause()

            app.query_input.text = "select"
            await pilot.pause()
            assert app.vim_mode == VimMode.NORMAL

            await pilot.press("tab")
            await pilot.pause()

            # Text should remain unchanged; Tab did not insert anything
            assert app.query_input.text == "select"
