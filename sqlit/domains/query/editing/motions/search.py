"""Character search motions."""

from __future__ import annotations

from ..types import MotionResult, MotionType, Position, Range
from .common import _normalize


def motion_find_char(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move to next occurrence of char (f{char})."""
    lines, row, col = _normalize(text, row, col)
    start_pos = Position(row, col)

    if not char:
        return MotionResult(position=start_pos)

    line = lines[row]

    # Search forward from col+1
    for i in range(col + 1, len(line)):
        if line[i] == char:
            return MotionResult(
                position=Position(row, i),
                range=Range(start_pos, Position(row, i), MotionType.CHARWISE, True),
            )

    # Not found - stay in place
    return MotionResult(position=start_pos)


def motion_find_char_back(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move to previous occurrence of char (F{char})."""
    lines, row, col = _normalize(text, row, col)
    end_pos = Position(row, col)

    if not char:
        return MotionResult(position=end_pos)

    line = lines[row]

    # Search backward from col-1
    for i in range(col - 1, -1, -1):
        if line[i] == char:
            return MotionResult(
                position=Position(row, i),
                range=Range(Position(row, i), end_pos, MotionType.CHARWISE, True),
            )

    # Not found - stay in place
    return MotionResult(position=end_pos)


def motion_till_char(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move to just before next occurrence of char (t{char})."""
    _lines, row, col = _normalize(text, row, col)
    start_pos = Position(row, col)

    if not char:
        return MotionResult(position=start_pos)

    result = motion_find_char(text, row, col, char)
    if result.position.col > col:
        # Stop one before the found character
        new_col = result.position.col - 1
        return MotionResult(
            position=Position(row, new_col),
            range=Range(start_pos, Position(row, new_col), MotionType.CHARWISE, True),
        )
    return result


def motion_till_char_back(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move to just after previous occurrence of char (T{char})."""
    _lines, row, col = _normalize(text, row, col)
    end_pos = Position(row, col)

    if not char:
        return MotionResult(position=end_pos)

    result = motion_find_char_back(text, row, col, char)
    if result.position.col < col:
        # Stop one after the found character
        new_col = result.position.col + 1
        return MotionResult(
            position=Position(row, new_col),
            range=Range(Position(row, new_col), end_pos, MotionType.CHARWISE, True),
        )
    return result
