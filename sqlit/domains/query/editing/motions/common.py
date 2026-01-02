"""Shared helpers for motion calculations."""

from __future__ import annotations


def _normalize(text: str, row: int, col: int) -> tuple[list[str], int, int]:
    """Normalize text and cursor position."""
    lines = text.split("\n")
    if not lines:
        lines = [""]
    row = max(0, min(row, len(lines) - 1))
    col = max(0, min(col, len(lines[row])))
    return lines, row, col


def _is_word_char(ch: str) -> bool:
    """Check if character is a word character (vim 'word')."""
    return ch.isalnum() or ch == "_"


def _is_WORD_char(ch: str) -> bool:
    """Check if character is a WORD character (non-whitespace)."""
    return not ch.isspace()
