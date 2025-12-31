"""Unit tests for vim text objects."""

from __future__ import annotations

import pytest

from sqlit.domains.query.editing.types import Position
from sqlit.domains.query.editing.text_objects import (
    text_object_word,
    text_object_WORD,
    text_object_quote,
    text_object_bracket,
    get_text_object,
    TEXT_OBJECT_CHARS,
)


class TestWordTextObjects:
    """Tests for iw/aw text objects."""

    def test_text_object_word_inside(self) -> None:
        result = text_object_word("hello world", row=0, col=2, around=False)
        assert result is not None
        assert result.start == Position(0, 0)
        assert result.end == Position(0, 4)  # 'hello' (0-4 inclusive)

    def test_text_object_word_around(self) -> None:
        result = text_object_word("hello world", row=0, col=2, around=True)
        assert result is not None
        assert result.start == Position(0, 0)
        assert result.end == Position(0, 5)  # 'hello ' (including trailing space)

    def test_text_object_word_on_punctuation(self) -> None:
        result = text_object_word("foo.bar", row=0, col=3, around=False)
        assert result is not None
        # Should select just the '.'
        assert result.start.col == 3
        assert result.end.col == 3

    def test_text_object_word_empty_line(self) -> None:
        result = text_object_word("", row=0, col=0, around=False)
        assert result is None


class TestWORDTextObjects:
    """Tests for iW/aW text objects."""

    def test_text_object_WORD_inside(self) -> None:
        result = text_object_WORD("foo.bar baz", row=0, col=2, around=False)
        assert result is not None
        assert result.start == Position(0, 0)
        assert result.end == Position(0, 6)  # 'foo.bar' (0-6 inclusive)

    def test_text_object_WORD_around(self) -> None:
        result = text_object_WORD("foo.bar baz", row=0, col=2, around=True)
        assert result is not None
        assert result.start == Position(0, 0)
        assert result.end == Position(0, 7)  # 'foo.bar ' (including space)

    def test_text_object_WORD_on_whitespace(self) -> None:
        result = text_object_WORD("foo   bar", row=0, col=4, around=False)
        assert result is None  # Cursor on whitespace


class TestQuoteTextObjects:
    """Tests for i"/a", i'/a' text objects."""

    def test_text_object_double_quote_inside(self) -> None:
        result = text_object_quote('say "hello"', row=0, col=6, around=False, quote='"')
        assert result is not None
        assert result.start == Position(0, 5)
        assert result.end == Position(0, 9)  # 'hello' without quotes

    def test_text_object_double_quote_around(self) -> None:
        result = text_object_quote('say "hello"', row=0, col=6, around=True, quote='"')
        assert result is not None
        assert result.start == Position(0, 4)
        assert result.end == Position(0, 10)  # '"hello"' with quotes

    def test_text_object_single_quote(self) -> None:
        result = text_object_quote("say 'hello'", row=0, col=6, around=False, quote="'")
        assert result is not None
        assert result.start == Position(0, 5)
        assert result.end == Position(0, 9)

    def test_text_object_quote_cursor_outside(self) -> None:
        # Cursor before quotes, should find next quoted string
        result = text_object_quote('say "hello"', row=0, col=0, around=False, quote='"')
        assert result is not None

    def test_text_object_quote_no_quotes(self) -> None:
        result = text_object_quote("no quotes here", row=0, col=5, around=False, quote='"')
        assert result is None


class TestBracketTextObjects:
    """Tests for i(/a(, i{/a{, i[/a[ text objects."""

    def test_text_object_paren_inside(self) -> None:
        result = text_object_bracket("(hello)", row=0, col=3, around=False, open_bracket="(")
        assert result is not None
        assert result.start == Position(0, 1)
        assert result.end == Position(0, 5)  # 'hello'

    def test_text_object_paren_around(self) -> None:
        result = text_object_bracket("(hello)", row=0, col=3, around=True, open_bracket="(")
        assert result is not None
        assert result.start == Position(0, 0)
        assert result.end == Position(0, 6)  # '(hello)'

    def test_text_object_curly_inside(self) -> None:
        result = text_object_bracket("{foo}", row=0, col=2, around=False, open_bracket="{")
        assert result is not None
        assert result.start == Position(0, 1)
        assert result.end == Position(0, 3)  # 'foo'

    def test_text_object_square_inside(self) -> None:
        result = text_object_bracket("[bar]", row=0, col=2, around=False, open_bracket="[")
        assert result is not None
        assert result.start == Position(0, 1)
        assert result.end == Position(0, 3)  # 'bar'

    def test_text_object_nested_brackets(self) -> None:
        result = text_object_bracket("((inner))", row=0, col=3, around=False, open_bracket="(")
        assert result is not None
        # Should find innermost brackets
        assert result.start == Position(0, 2)
        assert result.end == Position(0, 6)

    def test_text_object_multiline_brackets(self) -> None:
        text = "(\n  inner\n)"
        result = text_object_bracket(text, row=1, col=3, around=False, open_bracket="(")
        assert result is not None
        assert result.start == Position(0, 1)
        assert result.end == Position(2, -1)  # Before closing )

    def test_text_object_bracket_no_match(self) -> None:
        result = text_object_bracket("no brackets", row=0, col=5, around=False, open_bracket="(")
        assert result is None


class TestGetTextObject:
    """Tests for the get_text_object dispatcher."""

    def test_get_text_object_word(self) -> None:
        result = get_text_object("w", "hello world", row=0, col=2, around=False)
        assert result is not None

    def test_get_text_object_WORD(self) -> None:
        result = get_text_object("W", "foo.bar baz", row=0, col=2, around=False)
        assert result is not None

    def test_get_text_object_double_quote(self) -> None:
        result = get_text_object('"', 'say "hello"', row=0, col=6, around=False)
        assert result is not None

    def test_get_text_object_paren(self) -> None:
        result = get_text_object("(", "(hello)", row=0, col=3, around=False)
        assert result is not None

    def test_get_text_object_b_alias(self) -> None:
        # 'b' is alias for ()
        result = get_text_object("b", "(hello)", row=0, col=3, around=False)
        assert result is not None

    def test_get_text_object_B_alias(self) -> None:
        # 'B' is alias for {}
        result = get_text_object("B", "{hello}", row=0, col=3, around=False)
        assert result is not None

    def test_get_text_object_unknown(self) -> None:
        result = get_text_object("x", "hello", row=0, col=2, around=False)
        assert result is None


class TestTextObjectRegistry:
    """Tests for TEXT_OBJECT_CHARS registry."""

    def test_all_text_objects_registered(self) -> None:
        expected = {
            "w", "W",
            '"', "'", "`",
            "(", ")", "b",
            "[", "]",
            "{", "}", "B",
            "<", ">",
        }
        assert set(TEXT_OBJECT_CHARS.keys()) == expected
