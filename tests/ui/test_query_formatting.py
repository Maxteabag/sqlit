"""Pilot-driven query formatting tests."""

from __future__ import annotations

import pytest

from sqlit.domains.shell.app.main import SSMSTUI

from .mocks import MockConnectionStore, MockSettingsStore, build_test_services


def _make_app() -> SSMSTUI:
    return SSMSTUI(
        services=build_test_services(
            connection_store=MockConnectionStore(),
            settings_store=MockSettingsStore({"theme": "tokyo-night"}),
        )
    )


@pytest.mark.asyncio
async def test_space_p_formats_query_through_real_key_dispatch() -> None:
    app = _make_app()

    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        app.action_focus_query()
        app.query_input.text = "select id,name from users where active=true"
        await pilot.press("space", "p")
        await pilot.pause()

        assert app.query_input.text == """SELECT id,
       name
FROM users
WHERE active = TRUE"""


@pytest.mark.asyncio
async def test_format_action_is_undoable() -> None:
    app = _make_app()
    original = "select id,name from users"

    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        app.action_focus_query()
        app.query_input.text = original
        await pilot.press("space", "p")
        await pilot.pause()
        await pilot.press("u")
        await pilot.pause()

        assert app.query_input.text == original


@pytest.mark.asyncio
async def test_format_action_preserves_cursor_token() -> None:
    app = _make_app()
    query = "select id,name from users where active=true"

    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        app.action_focus_query()
        app.query_input.text = query
        app.query_input.cursor_location = (0, query.index("users") + len("users"))
        await pilot.press("space", "p")
        await pilot.pause()

        row, column = app.query_input.cursor_location
        assert app.query_input.text.splitlines()[row][:column].endswith("users")


@pytest.mark.asyncio
async def test_empty_query_is_not_changed() -> None:
    app = _make_app()

    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        app.action_focus_query()
        app.query_input.text = ""
        await pilot.press("space", "p")
        await pilot.pause()

        assert app.query_input.text == ""
        assert not app._get_undo_history().can_undo()
