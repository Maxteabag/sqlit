"""Linewise motions."""

from __future__ import annotations

from ..types import MotionResult, MotionType, Position, Range
from .common import _normalize


def motion_line_start(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move to start of line (0)."""
    _lines, row, col = _normalize(text, row, col)
    return MotionResult(
        position=Position(row, 0),
        range=Range(
            Position(row, 0),
            Position(row, col),
            MotionType.CHARWISE,
            inclusive=False,
        ),
    )


def motion_first_non_blank(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move to first non-whitespace character on line (^)."""
    lines, row, col = _normalize(text, row, col)
    line = lines[row]
    first_col = len(line) - len(line.lstrip())
    return MotionResult(
        position=Position(row, first_col),
        range=Range(
            Position(row, min(col, first_col)),
            Position(row, max(col, first_col)),
            MotionType.CHARWISE,
            inclusive=False,
        ),
    )


def motion_line_end(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move to end of line ($)."""
    lines, row, col = _normalize(text, row, col)
    end_col = len(lines[row])
    return MotionResult(
        position=Position(row, end_col),
        range=Range(
            Position(row, col),
            Position(row, end_col),
            MotionType.CHARWISE,
            inclusive=True,
        ),
    )


def motion_last_line(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move to last line (G)."""
    lines, row, col = _normalize(text, row, col)
    last_row = len(lines) - 1
    return MotionResult(
        position=Position(last_row, 0),
        range=Range(
            Position(row, 0),
            Position(last_row, len(lines[last_row])),
            MotionType.LINEWISE,
        ),
    )


def motion_first_line(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move to first line (gg)."""
    lines, row, col = _normalize(text, row, col)
    return MotionResult(
        position=Position(0, 0),
        range=Range(
            Position(0, 0),
            Position(row, len(lines[row])),
            MotionType.LINEWISE,
        ),
    )


def motion_current_line(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Operate on current line (_). Used for dd, yy, cc."""
    lines, row, col = _normalize(text, row, col)
    return MotionResult(
        position=Position(row, 0),
        range=Range(
            Position(row, 0),
            Position(row, len(lines[row])),
            MotionType.LINEWISE,
        ),
    )
