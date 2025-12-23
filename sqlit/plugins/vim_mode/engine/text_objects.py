"""Vim text object functions.

Text objects define ranges of text for operators to act on.
They're the "iw" in "diw", the "a(" in "ca(", etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from .state import TextObjectType

if TYPE_CHECKING:
    from .document import DocumentWrapper
    from .state import VimState


@dataclass
class TextObjectResult:
    """Result of a text object computation."""

    start: tuple[int, int]  # Start position (row, col)
    end: tuple[int, int]    # End position (row, col) - exclusive
    type: TextObjectType = TextObjectType.EXCLUSIVE
    failed: bool = False


# Type alias for text object functions
TextObjectFunc = Callable[["DocumentWrapper", "VimState", int], TextObjectResult]


# ─────────────────────────────────────────────────────────────────
# Word Objects (iw, aw, iW, aW)
# ─────────────────────────────────────────────────────────────────


def textobj_inner_word(doc: DocumentWrapper, state: VimState, count: int) -> TextObjectResult:
    """Inner word text object (iw)."""
    start_col, end_col = doc.get_word_boundaries(big_word=False)
    row = doc.cursor_row
    return TextObjectResult(
        start=(row, start_col),
        end=(row, end_col),
        type=TextObjectType.EXCLUSIVE,
    )


def textobj_outer_word(doc: DocumentWrapper, state: VimState, count: int) -> TextObjectResult:
    """A word text object including whitespace (aw)."""
    start_col, end_col = doc.get_outer_word_boundaries(big_word=False)
    row = doc.cursor_row
    return TextObjectResult(
        start=(row, start_col),
        end=(row, end_col),
        type=TextObjectType.EXCLUSIVE,
    )


def textobj_inner_word_big(doc: DocumentWrapper, state: VimState, count: int) -> TextObjectResult:
    """Inner WORD text object (iW)."""
    start_col, end_col = doc.get_word_boundaries(big_word=True)
    row = doc.cursor_row
    return TextObjectResult(
        start=(row, start_col),
        end=(row, end_col),
        type=TextObjectType.EXCLUSIVE,
    )


def textobj_outer_word_big(doc: DocumentWrapper, state: VimState, count: int) -> TextObjectResult:
    """A WORD text object including whitespace (aW)."""
    start_col, end_col = doc.get_outer_word_boundaries(big_word=True)
    row = doc.cursor_row
    return TextObjectResult(
        start=(row, start_col),
        end=(row, end_col),
        type=TextObjectType.EXCLUSIVE,
    )


# ─────────────────────────────────────────────────────────────────
# Quote Objects (i", a", i', a', i`, a`)
# ─────────────────────────────────────────────────────────────────


def _make_quote_textobj(quote_char: str, inner: bool) -> TextObjectFunc:
    """Factory for quote text object functions."""

    def textobj(doc: DocumentWrapper, state: VimState, count: int) -> TextObjectResult:
        result = doc.get_quote_boundaries(quote_char, inner=inner)
        if result is None:
            return TextObjectResult(
                start=doc.cursor_location,
                end=doc.cursor_location,
                failed=True,
            )
        start, end = result
        return TextObjectResult(start=start, end=end, type=TextObjectType.EXCLUSIVE)

    return textobj


textobj_inner_double_quote = _make_quote_textobj('"', inner=True)
textobj_outer_double_quote = _make_quote_textobj('"', inner=False)
textobj_inner_single_quote = _make_quote_textobj("'", inner=True)
textobj_outer_single_quote = _make_quote_textobj("'", inner=False)
textobj_inner_backtick = _make_quote_textobj("`", inner=True)
textobj_outer_backtick = _make_quote_textobj("`", inner=False)


# ─────────────────────────────────────────────────────────────────
# Bracket Objects (i(, a(, i[, a[, i{, a{, i<, a<)
# ─────────────────────────────────────────────────────────────────


def _make_bracket_textobj(open_char: str, close_char: str, inner: bool) -> TextObjectFunc:
    """Factory for bracket text object functions."""

    def textobj(doc: DocumentWrapper, state: VimState, count: int) -> TextObjectResult:
        result = doc.get_bracket_boundaries(open_char, close_char, inner=inner)
        if result is None:
            return TextObjectResult(
                start=doc.cursor_location,
                end=doc.cursor_location,
                failed=True,
            )
        start, end = result
        return TextObjectResult(start=start, end=end, type=TextObjectType.EXCLUSIVE)

    return textobj


textobj_inner_paren = _make_bracket_textobj("(", ")", inner=True)
textobj_outer_paren = _make_bracket_textobj("(", ")", inner=False)
textobj_inner_bracket = _make_bracket_textobj("[", "]", inner=True)
textobj_outer_bracket = _make_bracket_textobj("[", "]", inner=False)
textobj_inner_brace = _make_bracket_textobj("{", "}", inner=True)
textobj_outer_brace = _make_bracket_textobj("{", "}", inner=False)
textobj_inner_angle = _make_bracket_textobj("<", ">", inner=True)
textobj_outer_angle = _make_bracket_textobj("<", ">", inner=False)


# ─────────────────────────────────────────────────────────────────
# Text Object Registry
# ─────────────────────────────────────────────────────────────────

TEXT_OBJECT_HANDLERS: dict[str, TextObjectFunc] = {
    # Word objects
    "textobj_inner_word": textobj_inner_word,
    "textobj_outer_word": textobj_outer_word,
    "textobj_inner_word_big": textobj_inner_word_big,
    "textobj_outer_word_big": textobj_outer_word_big,
    # Quote objects
    "textobj_inner_double_quote": textobj_inner_double_quote,
    "textobj_outer_double_quote": textobj_outer_double_quote,
    "textobj_inner_single_quote": textobj_inner_single_quote,
    "textobj_outer_single_quote": textobj_outer_single_quote,
    "textobj_inner_backtick": textobj_inner_backtick,
    "textobj_outer_backtick": textobj_outer_backtick,
    # Bracket objects
    "textobj_inner_paren": textobj_inner_paren,
    "textobj_outer_paren": textobj_outer_paren,
    "textobj_inner_bracket": textobj_inner_bracket,
    "textobj_outer_bracket": textobj_outer_bracket,
    "textobj_inner_brace": textobj_inner_brace,
    "textobj_outer_brace": textobj_outer_brace,
    "textobj_inner_angle": textobj_inner_angle,
    "textobj_outer_angle": textobj_outer_angle,
}


def get_text_object_handler(name: str) -> TextObjectFunc | None:
    """Get a text object function by handler name."""
    return TEXT_OBJECT_HANDLERS.get(name)
