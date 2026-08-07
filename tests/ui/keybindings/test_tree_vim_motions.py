"""UI tests for vim motion keybindings in the explorer tree."""

from __future__ import annotations

import pytest

from sqlit.domains.shell.app.main import SSMSTUI

from ..mocks import MockConnectionStore, MockSettingsStore, build_test_services, create_test_connection


def _make_app(connection_count: int) -> SSMSTUI:
    connections = [create_test_connection(f"conn-{i:02d}", "sqlite") for i in range(connection_count)]
    services = build_test_services(
        connection_store=MockConnectionStore(connections),
        settings_store=MockSettingsStore({"theme": "tokyo-night"}),
    )
    return SSMSTUI(services=services)


class TestTreeVimMotions:
    """Vim scroll motions bound to the explorer tree."""

    @pytest.mark.asyncio
    async def test_G_jumps_to_last_node(self) -> None:
        app = _make_app(connection_count=20)
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_explorer()
            await pilot.pause()
            assert app.object_tree.has_focus

            await pilot.press("g", "g")
            await pilot.pause()
            assert app.object_tree.cursor_line == 0

            await pilot.press("G")
            await pilot.pause()
            assert app.object_tree.cursor_line == app.object_tree.last_line

    @pytest.mark.asyncio
    async def test_gg_jumps_to_first_node(self) -> None:
        app = _make_app(connection_count=20)
        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_explorer()
            await pilot.pause()

            await pilot.press("G")
            await pilot.pause()
            assert app.object_tree.cursor_line == app.object_tree.last_line

            await pilot.press("g", "g")
            await pilot.pause()
            assert app.object_tree.cursor_line == 0

    def test_scroll_motions_documented_in_help(self) -> None:
        from sqlit.domains.shell.state.help_doc import render_section
        from sqlit.domains.shell.state.machine import UIStateMachine

        explorer = next(s for s in UIStateMachine().generate_help_sections() if s.id == "explorer")
        descriptions = {item.description for item in explorer.items}
        assert "Page down/up" in descriptions
        assert "Jump to first node" in descriptions
        assert "Jump to last node" in descriptions

        rendered, _ = render_section(explorer)
        assert "gg" in rendered
        assert "G" in rendered

    @pytest.mark.asyncio
    async def test_ctrl_d_and_ctrl_u_page(self) -> None:
        app = _make_app(connection_count=60)
        async with app.run_test(size=(100, 20)) as pilot:
            app.action_focus_explorer()
            await pilot.pause()

            await pilot.press("g", "g")
            await pilot.pause()
            start_line = app.object_tree.cursor_line
            assert start_line == 0

            await pilot.press("ctrl+d")
            await pilot.pause()
            after_page_down = app.object_tree.cursor_line
            assert after_page_down > start_line, "ctrl+d should move the cursor down by a page"

            await pilot.press("ctrl+u")
            await pilot.pause()
            after_page_up = app.object_tree.cursor_line
            assert after_page_up < after_page_down, "ctrl+u should move the cursor up again"
