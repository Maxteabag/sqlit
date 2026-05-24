"""UI tests for autocomplete dropdown widget."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from sqlit.shared.ui.widgets_autocomplete import AutocompleteDropdown


class _DropdownTestApp(App):
    """Minimal app that mounts an AutocompleteDropdown for testing."""

    def compose(self) -> ComposeResult:
        yield AutocompleteDropdown()


class TestAutocompleteDropdownWidth:
    """Tests for dynamic width sizing based on filtered items."""

    @pytest.mark.asyncio
    async def test_empty_items_uses_min_width(self) -> None:
        """Width should be MIN_WIDTH when there are no filtered items."""
        app = _DropdownTestApp()
        async with app.run_test() as pilot:
            dropdown = app.query_one(AutocompleteDropdown)
            dropdown.set_items([])
            await pilot.pause()

            assert dropdown.styles.width is not None
            assert dropdown.styles.width.value == AutocompleteDropdown.MIN_WIDTH

    @pytest.mark.asyncio
    async def test_short_items_clamped_to_min_width(self) -> None:
        """Items shorter than MIN_WIDTH should result in width clamped to MIN_WIDTH."""
        app = _DropdownTestApp()
        async with app.run_test() as pilot:
            dropdown = app.query_one(AutocompleteDropdown)
            dropdown.set_items(["ab", "cd"])
            await pilot.pause()

            assert dropdown.styles.width is not None
            assert dropdown.styles.width.value == AutocompleteDropdown.MIN_WIDTH

    @pytest.mark.asyncio
    async def test_width_grows_with_longer_items(self) -> None:
        """Longer items should produce a wider dropdown than shorter items."""
        app = _DropdownTestApp()
        async with app.run_test() as pilot:
            dropdown = app.query_one(AutocompleteDropdown)

            dropdown.set_items(["short"])
            await pilot.pause()
            assert dropdown.styles.width is not None
            width_short = dropdown.styles.width.value

            dropdown.set_items(["a_much_longer_item_name_here"])
            await pilot.pause()
            assert dropdown.styles.width is not None
            width_long = dropdown.styles.width.value

            assert width_long > width_short

    @pytest.mark.asyncio
    async def test_long_items_clamped_to_max_width(self) -> None:
        """Items with length exceeding MAX_WIDTH should be clamped to MAX_WIDTH."""
        app = _DropdownTestApp()
        async with app.run_test() as pilot:
            dropdown = app.query_one(AutocompleteDropdown)
            dropdown.set_items(["a" * 100])
            await pilot.pause()

            assert dropdown.styles.width is not None
            assert dropdown.styles.width.value == AutocompleteDropdown.MAX_WIDTH

    @pytest.mark.asyncio
    async def test_scrollbar_width_added_when_items_exceed_max_height(self) -> None:
        """Width should include scrollbar allowance when item count exceeds MAX_HEIGHT."""
        app = _DropdownTestApp()
        async with app.run_test() as pilot:
            dropdown = app.query_one(AutocompleteDropdown)
            item = "x" * 20

            # Exactly MAX_HEIGHT items — no scrollbar
            dropdown.set_items([item] * AutocompleteDropdown.MAX_HEIGHT)
            await pilot.pause()
            assert dropdown.styles.width is not None
            width_at_max_height = dropdown.styles.width.value

            # More than MAX_HEIGHT — scrollbar kicks in
            dropdown.set_items([item] * (AutocompleteDropdown.MAX_HEIGHT + 1))
            await pilot.pause()
            assert dropdown.styles.width is not None
            width_over_max_height = dropdown.styles.width.value

            assert width_over_max_height == width_at_max_height + AutocompleteDropdown.VERTICAL_SCROLLBAR_SIZE
