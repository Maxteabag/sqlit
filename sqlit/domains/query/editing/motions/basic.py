"""Basic cursor motions."""

from __future__ import annotations

from ..types import MotionResult, MotionType, Position, Range
from .common import _normalize


def motion_left(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move cursor left (h)."""
    _lines, row, col = _normalize(text, row, col)
    new_col = max(0, col - 1)
    return MotionResult(
        position=Position(row, new_col),
        range=Range(
            Position(row, new_col),
            Position(row, col),
            MotionType.CHARWISE,
            inclusive=False,
        ),
    )


def motion_down(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move cursor down (j)."""
    lines, row, col = _normalize(text, row, col)
    new_row = min(row + 1, len(lines) - 1)
    new_col = min(col, len(lines[new_row]))
    return MotionResult(
        position=Position(new_row, new_col),
        range=Range(
            Position(row, 0),
            Position(new_row, len(lines[new_row])),
            MotionType.LINEWISE,
        ),
    )


def motion_up(text: str, row: int, col: int, char: str | None = None) -> MotionResult:
    """Move cursor up (k)."""
    lines, row, col = _normalize(text, row, col)
    new_row = max(0, row - 1)
    new_col = min(col, len(lines[new_row]))
    return MotionResult(
        position=Position(new_row, new_col),
        range=Range(
            Position(new_row, 0),
            Position(row, len(lines[row])),
            MotionType.LINEWISE,
        ),
    )


def motion_right(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move cursor right (l)."""
    lines, row, col = _normalize(text, row, col)
    new_col = min(col + 1, len(lines[row]))
    return MotionResult(
        position=Position(row, new_col),
        range=Range(
            Position(row, col),
            Position(row, new_col),
            MotionType.CHARWISE,
            inclusive=True,
        ),
    )
