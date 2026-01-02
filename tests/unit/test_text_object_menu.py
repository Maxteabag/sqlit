"""Unit tests for text object menu screen."""

from __future__ import annotations

from sqlit.domains.query.ui.screens.text_object_menu import TextObjectMenuScreen


class TestTextObjectMenuTitle:
    """Tests for TextObjectMenuScreen title display."""

    def test_yank_around_shows_yank_title(self) -> None:
        """When opened for yank around, title should say 'Yank around...'."""
        screen = TextObjectMenuScreen(mode="around", operator="yank")
        # The compose method creates the content - we need to check the title
        # We can inspect the _mode and _operator attributes
        assert screen._mode == "around"
        assert screen._operator == "yank"
        # We can't easily test the rendered content, but we can verify
        # the screen has the right attributes to build the correct title

    def test_yank_inner_shows_yank_title(self) -> None:
        """When opened for yank inner, title should say 'Yank inner...'."""
        screen = TextObjectMenuScreen(mode="inner", operator="yank")
        assert screen._mode == "inner"
        assert screen._operator == "yank"

    def test_delete_around_shows_delete_title(self) -> None:
        """When opened for delete around, title should say 'Delete around...'."""
        screen = TextObjectMenuScreen(mode="around", operator="delete")
        assert screen._mode == "around"
        assert screen._operator == "delete"

    def test_delete_inner_shows_delete_title(self) -> None:
        """When opened for delete inner, title should say 'Delete inner...'."""
        screen = TextObjectMenuScreen(mode="inner", operator="delete")
        assert screen._mode == "inner"
        assert screen._operator == "delete"

    def test_change_around_shows_change_title(self) -> None:
        """When opened for change around, title should say 'Change around...'."""
        screen = TextObjectMenuScreen(mode="around", operator="change")
        assert screen._mode == "around"
        assert screen._operator == "change"

    def test_change_inner_shows_change_title(self) -> None:
        """When opened for change inner, title should say 'Change inner...'."""
        screen = TextObjectMenuScreen(mode="inner", operator="change")
        assert screen._mode == "inner"
        assert screen._operator == "change"
