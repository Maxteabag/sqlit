"""Bracket matching motion."""

from __future__ import annotations

from ..types import MotionResult, MotionType, Position, Range
from .common import _normalize

BRACKET_PAIRS = {
    "(": ")",
    ")": "(",
    "[": "]",
    "]": "[",
    "{": "}",
    "}": "{",
}


def motion_matching_bracket(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move to matching bracket (%)."""
    lines, row, col = _normalize(text, row, col)
    start_pos = Position(row, col)

    if col >= len(lines[row]):
        return MotionResult(position=start_pos)

    line = lines[row]
    ch = line[col]

    if ch not in BRACKET_PAIRS:
        # Search forward on current line for a bracket
        for i in range(col, len(line)):
            if line[i] in BRACKET_PAIRS:
                col = i
                ch = line[i]
                break
        else:
            return MotionResult(position=start_pos)

    target = BRACKET_PAIRS[ch]
    forward = ch in "([{"
    depth = 1

    if forward:
        r, c = row, col + 1
        while r < len(lines):
            while c < len(lines[r]):
                if lines[r][c] == ch:
                    depth += 1
                elif lines[r][c] == target:
                    depth -= 1
                    if depth == 0:
                        return MotionResult(
                            position=Position(r, c),
                            range=Range(
                                start_pos, Position(r, c), MotionType.CHARWISE, True
                            ),
                        )
                c += 1
            r += 1
            c = 0
    else:
        r, c = row, col - 1
        while r >= 0:
            while c >= 0:
                if lines[r][c] == ch:
                    depth += 1
                elif lines[r][c] == target:
                    depth -= 1
                    if depth == 0:
                        return MotionResult(
                            position=Position(r, c),
                            range=Range(
                                Position(r, c), start_pos, MotionType.CHARWISE, True
                            ),
                        )
                c -= 1
            r -= 1
            if r >= 0:
                c = len(lines[r]) - 1

    return MotionResult(position=start_pos)
