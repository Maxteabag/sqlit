"""UI tests for pane resize keybindings and persistence."""

from __future__ import annotations

import pytest

from sqlit.core.keymap import get_keymap
from sqlit.domains.shell.app.main import SSMSTUI
from sqlit.shared.ui.widgets_pane_splitter import PaneSplitter

from ..mocks import MockConnectionStore, MockSettingsStore, build_test_services


class _FakeMouseEvent:
    """Minimal stand-in for a textual Mouse* event used to drive splitters."""

    def __init__(self, delta_x: int = 0, delta_y: int = 0) -> None:
        self.delta_x = delta_x
        self.delta_y = delta_y
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


def _make_app(settings: dict | None = None) -> SSMSTUI:
    services = build_test_services(
        connection_store=MockConnectionStore(),
        settings_store=MockSettingsStore({"theme": "tokyo-night", **(settings or {})}),
    )
    return SSMSTUI(services=services)


def _width(app: SSMSTUI) -> int | None:
    scalar = app.sidebar.styles.width
    return int(scalar.value) if scalar is not None else None


def _query_height(app: SSMSTUI) -> int | None:
    scalar = app.query_area.styles.height
    return int(scalar.value) if scalar is not None else None


class TestPaneResizeRegistration:
    def test_leader_actions_registered_in_keymap(self) -> None:
        km = get_keymap()
        leader = {c.action for c in km.get_leader_commands()}
        assert {"grow_active_pane", "shrink_active_pane"} <= leader

    def test_direct_resize_keys_unbound_by_default(self) -> None:
        # ctrl+arrow clashes with macOS Spaces/Mission Control, so the direct
        # resize actions ship with no default key (still rebindable).
        km = get_keymap()
        actions = {a.action for a in km.get_action_keys()}
        assert not ({"grow_sidebar", "shrink_sidebar", "grow_split", "shrink_split"} & actions)

    def test_action_methods_exist(self) -> None:
        for name in (
            "action_grow_sidebar",
            "action_shrink_sidebar",
            "action_grow_split",
            "action_shrink_split",
            "action_grow_active_pane",
            "action_shrink_active_pane",
        ):
            assert hasattr(SSMSTUI, name), name


class TestSidebarResize:
    @pytest.mark.asyncio
    async def test_grow_and_shrink(self) -> None:
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            app.action_focus_explorer()
            await pilot.pause()
            start = _width(app) or 35

            app.action_grow_sidebar()
            await pilot.pause()
            assert _width(app) == start + app._RESIZE_STEP

            app.action_shrink_sidebar()
            await pilot.pause()
            assert _width(app) == start

    @pytest.mark.asyncio
    async def test_clamped_at_bounds(self) -> None:
        app = _make_app()
        async with app.run_test(size=(160, 40)) as pilot:
            app.action_focus_explorer()
            await pilot.pause()
            for _ in range(40):
                app.action_grow_sidebar()
                await pilot.pause()
            assert _width(app) == app._SIDEBAR_MAX
            for _ in range(40):
                app.action_shrink_sidebar()
                await pilot.pause()
            assert _width(app) == app._SIDEBAR_MIN

    @pytest.mark.asyncio
    async def test_count_prefix_multiplies_step(self) -> None:
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            app.action_focus_explorer()
            await pilot.pause()
            start = _width(app) or 35
            app._count_buffer = "3"
            app.action_grow_sidebar()
            await pilot.pause()
            assert _width(app) == start + 3 * app._RESIZE_STEP


class TestSplitResize:
    @pytest.mark.asyncio
    async def test_query_height_changes_results_absorbs(self) -> None:
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            app.action_focus_query()
            await pilot.pause()
            # Default height is a % rule; measure the rendered cell height.
            before_cells = app.query_area.size.height

            app.action_grow_split()
            await pilot.pause()
            # After resizing, height is pinned in cells and larger than before.
            scalar = app.query_area.styles.height
            assert scalar is not None and scalar.unit.name == "CELLS"
            assert int(scalar.value) == before_cells + app._RESIZE_STEP
            # results-area stays flexible (fr), never pinned to cells
            results_scalar = app.results_area.styles.height
            assert results_scalar is None or results_scalar.unit.name != "CELLS"


class TestLeaderKeyResize:
    @pytest.mark.asyncio
    async def test_space_equals_and_minus_resize_focused_pane(self) -> None:
        # End-to-end through the leader menu. '=' / '-' are Textual key names
        # equals_sign / minus; a raw "=" binding would never match the event.
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            app.action_focus_explorer()
            await pilot.pause()
            start = _width(app) or 35

            await pilot.press("space")
            await pilot.pause()
            await pilot.press("=")
            await pilot.pause()
            assert _width(app) == start + app._RESIZE_STEP

            await pilot.press("space")
            await pilot.pause()
            await pilot.press("-")
            await pilot.pause()
            assert _width(app) == start


class TestActivePaneResize:
    @pytest.mark.asyncio
    async def test_leader_targets_focused_boundary(self) -> None:
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            app.action_focus_explorer()
            await pilot.pause()
            start = _width(app) or 35
            app.action_grow_active_pane()
            await pilot.pause()
            assert _width(app) == start + app._RESIZE_STEP

            app.action_focus_query()
            await pilot.pause()
            width_after = _width(app)
            app.action_grow_active_pane()
            await pilot.pause()
            # sidebar untouched when query focused
            assert _width(app) == width_after


class TestPersistence:
    @pytest.mark.asyncio
    async def test_resize_persists_to_settings(self) -> None:
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            app.action_focus_explorer()
            await pilot.pause()
            app.action_grow_sidebar()
            await pilot.pause()
            assert app.services.settings_store.get("sidebar_width") == _width(app)

    @pytest.mark.asyncio
    async def test_persisted_width_reapplied_on_startup(self) -> None:
        app = _make_app({"sidebar_width": 50})
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert _width(app) == 50

    @pytest.mark.asyncio
    async def test_persisted_width_clamped_on_startup(self) -> None:
        app = _make_app({"sidebar_width": 9999})
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert _width(app) == app._SIDEBAR_MAX


class TestSplitterRender:
    @pytest.mark.asyncio
    async def test_splitters_render_blank_not_css_identifier(self) -> None:
        # Regression: a bare Widget.render() leaks the CSS identifier as text.
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            for sid in ("#sidebar-splitter", "#query-results-splitter"):
                splitter = app.query_one(sid, PaneSplitter)
                rendered = splitter.render()
                assert str(getattr(rendered, "plain", rendered)) == ""


class TestMouseDragResize:
    @pytest.mark.asyncio
    async def test_vertical_drag_grows_sidebar_and_persists(self) -> None:
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            app.action_focus_explorer()
            await pilot.pause()
            splitter = app.query_one("#sidebar-splitter", PaneSplitter)
            start = _width(app) or 35

            splitter.on_mouse_down(_FakeMouseEvent())
            await pilot.pause()
            assert splitter._dragging is True

            splitter.on_mouse_move(_FakeMouseEvent(delta_x=6))
            await pilot.pause()
            # positive delta_x widens the sidebar
            assert _width(app) == start + 6

            splitter.on_mouse_up(_FakeMouseEvent())
            await pilot.pause()
            # drag flag resets and the final size is persisted
            assert splitter._dragging is False
            assert app.services.settings_store.get("sidebar_width") == _width(app)

    @pytest.mark.asyncio
    async def test_vertical_drag_clamps_at_max(self) -> None:
        app = _make_app()
        async with app.run_test(size=(160, 40)) as pilot:
            app.action_focus_explorer()
            await pilot.pause()
            splitter = app.query_one("#sidebar-splitter", PaneSplitter)
            splitter._dragging = True
            splitter.on_mouse_move(_FakeMouseEvent(delta_x=9999))
            await pilot.pause()
            assert _width(app) == app._SIDEBAR_MAX

    @pytest.mark.asyncio
    async def test_horizontal_drag_grows_query_height(self) -> None:
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            app.action_focus_query()
            await pilot.pause()
            splitter = app.query_one("#query-results-splitter", PaneSplitter)
            before_cells = app.query_area.size.height

            splitter._dragging = True
            splitter.on_mouse_move(_FakeMouseEvent(delta_y=5))
            await pilot.pause()
            scalar = app.query_area.styles.height
            assert scalar is not None and scalar.unit.name == "CELLS"
            assert int(scalar.value) == before_cells + 5

            splitter.on_mouse_up(_FakeMouseEvent())
            await pilot.pause()
            assert splitter._dragging is False
            assert app.services.settings_store.get("query_area_height") == _query_height(app)

    @pytest.mark.asyncio
    async def test_move_without_drag_is_ignored(self) -> None:
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            app.action_focus_explorer()
            await pilot.pause()
            splitter = app.query_one("#sidebar-splitter", PaneSplitter)
            start = _width(app) or 35
            # no mouse-down yet -> not dragging -> ignored
            splitter.on_mouse_move(_FakeMouseEvent(delta_x=6))
            await pilot.pause()
            assert _width(app) == start

    @pytest.mark.asyncio
    async def test_mouse_up_without_drag_is_a_noop(self) -> None:
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            app.action_focus_explorer()
            await pilot.pause()
            splitter = app.query_one("#sidebar-splitter", PaneSplitter)
            assert splitter._dragging is False
            event = _FakeMouseEvent()
            # A stray mouse-up (no preceding mouse-down) must not persist,
            # release the (uncaptured) mouse, or consume the event.
            splitter.on_mouse_up(event)
            await pilot.pause()
            assert splitter._dragging is False
            assert event.stopped is False
            assert app.services.settings_store.get("sidebar_width") is None

    @pytest.mark.asyncio
    async def test_horizontal_drag_clamps_at_min(self) -> None:
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            app.action_focus_query()
            await pilot.pause()
            splitter = app.query_one("#query-results-splitter", PaneSplitter)
            splitter._dragging = True
            # A large negative delta_y shrinks the query pane past its floor.
            splitter.on_mouse_move(_FakeMouseEvent(delta_y=-9999))
            await pilot.pause()
            assert _query_height(app) == app._QUERY_MIN


class TestFullscreenInteraction:
    @pytest.mark.asyncio
    async def test_inline_width_cleared_in_fullscreen_restored_after(self) -> None:
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            app.action_focus_explorer()
            await pilot.pause()
            app.action_grow_sidebar()
            await pilot.pause()
            resized = _width(app)

            app._set_fullscreen_mode("explorer")
            await pilot.pause()
            # inline width dropped so fullscreen CSS (width: 1fr) wins
            assert app.sidebar.styles.width is None or app.sidebar.styles.width.unit.name != "CELLS"

            app._set_fullscreen_mode("none")
            await pilot.pause()
            assert _width(app) == resized

    @pytest.mark.asyncio
    async def test_splitters_hidden_in_fullscreen_modes(self) -> None:
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            sidebar_splitter = app.query_one("#sidebar-splitter")
            query_splitter = app.query_one("#query-results-splitter")

            # Both splitters visible in the normal layout.
            assert sidebar_splitter.display is True
            assert query_splitter.display is True

            # explorer-fullscreen: main-panel (and its splitter) gone,
            # sidebar-splitter hidden too since there is nothing to divide.
            app._set_fullscreen_mode("explorer")
            await pilot.pause()
            assert sidebar_splitter.display is False
            assert query_splitter.display is False

            # results-fullscreen: sidebar is hidden, so its splitter must be too.
            app._set_fullscreen_mode("results")
            await pilot.pause()
            assert sidebar_splitter.display is False
            assert query_splitter.display is False

            # query-fullscreen: same expectation.
            app._set_fullscreen_mode("query")
            await pilot.pause()
            assert sidebar_splitter.display is False
            assert query_splitter.display is False

            # Back to normal: both splitters reappear.
            app._set_fullscreen_mode("none")
            await pilot.pause()
            assert sidebar_splitter.display is True
            assert query_splitter.display is True

    @pytest.mark.asyncio
    async def test_sidebar_splitter_hidden_when_explorer_hidden(self) -> None:
        app = _make_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            sidebar_splitter = app.query_one("#sidebar-splitter")
            assert sidebar_splitter.display is True

            app.action_toggle_explorer()
            await pilot.pause()
            assert app.screen.has_class("explorer-hidden")
            assert sidebar_splitter.display is False

            app.action_toggle_explorer()
            await pilot.pause()
            assert not app.screen.has_class("explorer-hidden")
            assert sidebar_splitter.display is True
