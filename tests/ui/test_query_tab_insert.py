"""UI tests for Tab behavior in the query editor."""

from __future__ import annotations

import pytest
from textual.widgets.text_area import Selection

from sqlit.core.keymap import ActionKeyDef, DefaultKeymapProvider, reset_keymap, set_keymap
from sqlit.core.vim import VimMode
from sqlit.domains.connections.providers.catalog import get_provider
from sqlit.domains.shell.app.keymap_manager import FileBasedKeymapProvider
from sqlit.domains.shell.app.main import SSMSTUI
from sqlit.shared.ui.widgets_autocomplete import AutocompleteItem

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

    @pytest.mark.parametrize(
        ("before", "after", "key", "accept", "expected"),
        [
            ("CREATE TABLE t (id INT GE", ");", "n", ("tab",), "CREATE TABLE t (id INT GENERATED"),
            ("CREATE TABLE t (id INT GENERATED ", ");", "a", ("tab",), "CREATE TABLE t (id INT GENERATED AS"),
            (
                "CREATE TABLE t (source INT, result INT GENERATED ALWAYS ",
                " (source + 1) STORED);",
                "a",
                ("tab",),
                "CREATE TABLE t (source INT, result INT GENERATED ALWAYS AS",
            ),
            (
                "CREATE TABLE books (id BIGINT GE",
                ", title text)",
                "n",
                ("down", "tab"),
                "CREATE TABLE books (id BIGINT GENERATED ALWAYS AS IDENTITY",
            ),
            (
                "ALTER TABLE altered ADD COLUMN id INTEGER GENERATED",
                "",
                "space",
                ("tab",),
                "ALTER TABLE altered ADD COLUMN id INTEGER GENERATED ALWAYS AS IDENTITY",
            ),
            (
                "/* publisher's schema */ CREATE TABLE t (source INT, -- publisher's id\n id INT GE",
                ");",
                "n",
                ("down", "tab"),
                "/* publisher's schema */ CREATE TABLE t (source INT, -- publisher's id\n id INT GENERATED ALWAYS AS IDENTITY",
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_postgres_generated_completions_accept_through_editor(self, before, after, key, accept, expected) -> None:
        app = _make_app()

        async with app.run_test(size=(120, 40)) as pilot:
            app.current_provider = get_provider("postgresql")
            app.current_connection = object()
            try:
                app.action_focus_query()
                await pilot.press("i")
                app.query_input.text = before + after
                app.query_input.cursor_location = (before.count("\n"), len(before.rsplit("\n", 1)[-1]))

                await pilot.press(key)
                await pilot.pause(0.15)
                typed = " " if key == "space" else key
                assert app.query_input.text == before + typed + after
                assert app._autocomplete_visible
                await pilot.press(*accept)
                await pilot.pause()

                assert app.query_input.text == expected + after
            finally:
                app.current_connection = None

    @pytest.mark.asyncio
    async def test_enter_inserts_newline_with_default_tab_accept_binding(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.press("i")
            app.query_input.text = "sel"
            app.query_input.cursor_location = (0, 3)
            app._show_autocomplete(["select", "set"], "sel")
            await pilot.pause()

            await pilot.press("enter")
            await pilot.pause()

            assert app._autocomplete_visible is False
            assert app.query_input.text == "sel\n"

    @pytest.mark.asyncio
    async def test_enter_accepts_autocomplete_when_explicitly_rebound(self) -> None:
        app = _make_app()

        try:
            async with app.run_test(size=(100, 35)) as pilot:
                app.action_focus_query()
                await pilot.press("i")
                defaults = DefaultKeymapProvider()
                action_keys = [
                    binding
                    for binding in defaults.get_action_keys()
                    if not (
                        binding.action == "autocomplete_accept"
                        and binding.context == "autocomplete"
                    )
                ]
                action_keys.append(
                    ActionKeyDef("enter", "autocomplete_accept", "autocomplete")
                )
                set_keymap(
                    FileBasedKeymapProvider(
                        "enter-to-accept",
                        defaults.get_leader_commands(),
                        action_keys,
                    )
                )
                app.query_input.text = "sel"
                app.query_input.cursor_location = (0, 3)
                app._show_autocomplete(["select", "set"], "sel")
                await pilot.pause()

                await pilot.press("enter")
                await pilot.pause()

                assert app._autocomplete_visible is False
                assert app.query_input.text == "select"
        finally:
            reset_keymap()

    @pytest.mark.asyncio
    async def test_clicking_autocomplete_suggestion_applies_clicked_item(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.press("i")
            app.query_input.text = "se"
            app.query_input.cursor_location = (0, 2)
            app._show_autocomplete(["select", "set"], "se")
            await pilot.pause()

            items = list(app.autocomplete_dropdown.query(AutocompleteItem))
            assert await pilot.click(items[1])
            await pilot.pause()

            assert app._autocomplete_visible is False
            assert app.query_input.text == "set"

    @pytest.mark.asyncio
    async def test_ctrl_enter_executes_in_insert_mode_without_newline(self) -> None:
        app = _make_app()
        calls: list[bool] = []
        app._execute_query_common = (  # type: ignore[method-assign]
            lambda *, keep_insert_mode: calls.append(keep_insert_mode)
        )

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.press("i")
            app.query_input.text = "select 1"
            await pilot.pause()

            await pilot.press("ctrl+enter")
            await pilot.pause()

            assert calls == [True]
            assert app.query_input.text == "select 1"

    @pytest.mark.asyncio
    async def test_enter_rebinding_executes_instead_of_inserting_newline(self) -> None:
        app = _make_app()
        calls: list[bool] = []
        app._execute_query_common = (  # type: ignore[method-assign]
            lambda *, keep_insert_mode: calls.append(keep_insert_mode)
        )

        try:
            async with app.run_test(size=(100, 35)) as pilot:
                app.action_focus_query()
                await pilot.press("i")
                defaults = DefaultKeymapProvider()
                action_keys = [
                    binding
                    for binding in defaults.get_action_keys()
                    if not (
                        binding.action == "execute_query_insert"
                        and binding.context == "query_insert"
                    )
                ]
                action_keys.append(
                    ActionKeyDef("enter", "execute_query_insert", "query_insert")
                )
                set_keymap(
                    FileBasedKeymapProvider(
                        "enter-to-execute",
                        defaults.get_leader_commands(),
                        action_keys,
                    )
                )
                app.query_input.text = "select 1"
                await pilot.pause()

                await pilot.press("enter")
                await pilot.pause()

                assert calls == [True]
                assert app.query_input.text == "select 1"
        finally:
            reset_keymap()

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

    @pytest.mark.asyncio
    async def test_tab_replaces_active_selection(self) -> None:
        app = _make_app()

        async with app.run_test(size=(100, 35)) as pilot:
            app.action_focus_query()
            await pilot.press("i")
            await pilot.pause()

            app.query_input.text = "abcd"
            app.query_input.selection = Selection((0, 1), (0, 3))
            await pilot.pause()

            await pilot.press("tab")
            await pilot.pause()

            assert app.query_input.text == "a\td"

    @pytest.mark.asyncio
    async def test_tab_inserts_when_autocomplete_accept_is_rebound(self) -> None:
        app = _make_app()

        try:
            async with app.run_test(size=(100, 35)) as pilot:
                app.action_focus_query()
                await pilot.press("i")
                await pilot.pause()

                defaults = DefaultKeymapProvider()
                action_keys = [
                    binding
                    for binding in defaults.get_action_keys()
                    if not (
                        binding.action == "autocomplete_accept"
                        and binding.context == "autocomplete"
                    )
                ]
                action_keys.append(
                    ActionKeyDef("ctrl+space", "autocomplete_accept", "autocomplete")
                )
                set_keymap(
                    FileBasedKeymapProvider(
                        "rebound-autocomplete",
                        defaults.get_leader_commands(),
                        action_keys,
                    )
                )

                app.query_input.text = "sel"
                app.query_input.cursor_location = (0, 3)
                app._show_autocomplete(["select", "set"], "sel")
                await pilot.pause()

                await pilot.press("tab")
                await pilot.pause()

                assert app.query_input.text == "sel\t"
        finally:
            reset_keymap()

    @pytest.mark.asyncio
    async def test_tab_honors_other_autocomplete_action_rebinding(self) -> None:
        app = _make_app()

        try:
            async with app.run_test(size=(100, 35)) as pilot:
                app.action_focus_query()
                await pilot.press("i")
                await pilot.pause()

                defaults = DefaultKeymapProvider()
                action_keys = [
                    binding
                    for binding in defaults.get_action_keys()
                    if not (
                        binding.key == "tab"
                        and binding.context == "autocomplete"
                    )
                ]
                action_keys.append(
                    ActionKeyDef("tab", "autocomplete_next", "autocomplete")
                )
                set_keymap(
                    FileBasedKeymapProvider(
                        "rebound-autocomplete-next",
                        defaults.get_leader_commands(),
                        action_keys,
                    )
                )

                app.query_input.text = "s"
                app.query_input.cursor_location = (0, 1)
                app._show_autocomplete(
                    ["select", "set", "session", "sequence", "security"],
                    "s",
                )
                await pilot.pause()
                assert app.autocomplete_dropdown.selected_index == 0

                await pilot.press("tab")
                await pilot.pause()

                assert app.query_input.text == "s"
                assert app.autocomplete_dropdown.selected_index == 1
        finally:
            reset_keymap()
