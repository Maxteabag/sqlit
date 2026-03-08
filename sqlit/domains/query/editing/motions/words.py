"""Word and WORD motions."""

from __future__ import annotations

from ..types import MotionResult, MotionType, Position, Range
from .common import _is_WORD_char, _is_word_char, _normalize


def motion_word(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move to start of next word (w)."""
    lines, row, col = _normalize(text, row, col)
    start_pos = Position(row, col)
    line = lines[row]

    # Skip current word
    while col < len(line) and _is_word_char(line[col]):
        col += 1
    # Skip punctuation if we started on word
    while col < len(line) and not _is_word_char(line[col]) and not line[col].isspace():
        col += 1
    # Skip whitespace
    while col < len(line) and line[col].isspace():
        col += 1

    # If at end of line, try next line
    if col >= len(line) and row < len(lines) - 1:
        row += 1
        col = 0
        line = lines[row]
        while col < len(line) and line[col].isspace():
            col += 1

    end_pos = Position(row, col)
    return MotionResult(
        position=end_pos,
        range=Range(start_pos, end_pos, MotionType.CHARWISE, inclusive=False),
    )


def motion_WORD(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move to start of next WORD (W) - whitespace-separated."""
    lines, row, col = _normalize(text, row, col)
    start_pos = Position(row, col)
    line = lines[row]

    # Skip current WORD (non-whitespace)
    while col < len(line) and _is_WORD_char(line[col]):
        col += 1
    # Skip whitespace
    while col < len(line) and line[col].isspace():
        col += 1

    # If at end of line, try next line
    if col >= len(line) and row < len(lines) - 1:
        row += 1
        col = 0
        line = lines[row]
        while col < len(line) and line[col].isspace():
            col += 1

    end_pos = Position(row, col)
    return MotionResult(
        position=end_pos,
        range=Range(start_pos, end_pos, MotionType.CHARWISE, inclusive=False),
    )


def motion_word_back(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move to start of previous word (b)."""
    lines, row, col = _normalize(text, row, col)
    end_pos = Position(row, col)
    line = lines[row]

    # If at start of line, go to previous line
    if col == 0 and row > 0:
        row -= 1
        col = len(lines[row])
        line = lines[row]

    # Skip whitespace backwards
    while col > 0 and line[col - 1].isspace():
        col -= 1

    # Skip to start of word
    if col > 0:
        if _is_word_char(line[col - 1]):
            while col > 0 and _is_word_char(line[col - 1]):
                col -= 1
        else:
            while (
                col > 0
                and not _is_word_char(line[col - 1])
                and not line[col - 1].isspace()
            ):
                col -= 1

    start_pos = Position(row, col)
    return MotionResult(
        position=start_pos,
        range=Range(start_pos, end_pos, MotionType.CHARWISE, inclusive=False),
    )


def motion_WORD_back(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move to start of previous WORD (B)."""
    lines, row, col = _normalize(text, row, col)
    end_pos = Position(row, col)
    line = lines[row]

    # If at start of line, go to previous line
    if col == 0 and row > 0:
        row -= 1
        col = len(lines[row])
        line = lines[row]

    # Skip whitespace backwards
    while col > 0 and line[col - 1].isspace():
        col -= 1

    # Skip to start of WORD
    while col > 0 and _is_WORD_char(line[col - 1]):
        col -= 1

    start_pos = Position(row, col)
    return MotionResult(
        position=start_pos,
        range=Range(start_pos, end_pos, MotionType.CHARWISE, inclusive=False),
    )


def motion_word_end(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move to end of current/next word (e)."""
    lines, row, col = _normalize(text, row, col)
    start_pos = Position(row, col)
    line = lines[row]

    # Move at least one character
    if col < len(line):
        col += 1

    # Skip whitespace
    while col < len(line) and line[col].isspace():
        col += 1

    # If at end of line, try next line
    if col >= len(line) and row < len(lines) - 1:
        row += 1
        col = 0
        line = lines[row]
        while col < len(line) and line[col].isspace():
            col += 1

    # Move to end of word
    if col < len(line):
        if _is_word_char(line[col]):
            while col < len(line) - 1 and _is_word_char(line[col + 1]):
                col += 1
        else:
            while (
                col < len(line) - 1
                and not _is_word_char(line[col + 1])
                and not line[col + 1].isspace()
            ):
                col += 1

    end_pos = Position(row, col)
    return MotionResult(
        position=end_pos,
        range=Range(start_pos, end_pos, MotionType.CHARWISE, inclusive=True),
    )


def motion_WORD_end(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move to end of current/next WORD (E)."""
    lines, row, col = _normalize(text, row, col)
    start_pos = Position(row, col)
    line = lines[row]

    # Move at least one character
    if col < len(line):
        col += 1

    # Skip whitespace
    while col < len(line) and line[col].isspace():
        col += 1

    # If at end of line, try next line
    if col >= len(line) and row < len(lines) - 1:
        row += 1
        col = 0
        line = lines[row]
        while col < len(line) and line[col].isspace():
            col += 1

    # Move to end of WORD
    while col < len(line) - 1 and _is_WORD_char(line[col + 1]):
        col += 1

    end_pos = Position(row, col)
    return MotionResult(
        position=end_pos,
        range=Range(start_pos, end_pos, MotionType.CHARWISE, inclusive=True),
    )


def motion_word_end_back(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move to end of previous word (ge).

    This is like 'e' motion but in reverse - moves to the last character
    of the previous word.
    """
    lines, row, col = _normalize(text, row, col)
    end_pos = Position(row, col)
    line = lines[row]

    # Move at least one character back
    if col > 0:
        col -= 1
    elif row > 0:
        row -= 1
        line = lines[row]
        col = len(line) - 1 if line else 0
    else:
        return MotionResult(
            position=Position(0, 0),
            range=Range(Position(0, 0), end_pos, MotionType.CHARWISE, inclusive=True),
        )

    # Skip through current word backwards to get before it
    if 0 <= col < len(line):
        ch = line[col]
        if _is_word_char(ch):
            # Skip word characters backwards to start of word
            while col > 0 and _is_word_char(line[col - 1]):
                col -= 1
            col -= 1  # Move to character before the word
        elif not ch.isspace():
            # On punctuation - skip punctuation backwards
            while (
                col > 0
                and not _is_word_char(line[col - 1])
                and not line[col - 1].isspace()
            ):
                col -= 1
            col -= 1  # Move to character before the punctuation

    # Handle going past start of line
    if col < 0:
        if row > 0:
            row -= 1
            line = lines[row]
            col = len(line) - 1 if line else 0
        else:
            col = 0

    # Skip whitespace backwards
    while 0 <= col < len(line) and line[col].isspace():
        col -= 1
        if col < 0 and row > 0:
            row -= 1
            line = lines[row]
            col = len(line) - 1 if line else 0

    start_pos = Position(row, max(0, col))
    return MotionResult(
        position=start_pos,
        range=Range(start_pos, end_pos, MotionType.CHARWISE, inclusive=True),
    )


def motion_WORD_end_back(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move to end of previous WORD (gE).

    Like ge but for WORDs (whitespace-separated).
    """
    lines, row, col = _normalize(text, row, col)
    end_pos = Position(row, col)
    line = lines[row]

    # Move at least one character back
    if col > 0:
        col -= 1
    elif row > 0:
        row -= 1
        line = lines[row]
        col = len(line) - 1 if line else 0
    else:
        return MotionResult(
            position=Position(0, 0),
            range=Range(Position(0, 0), end_pos, MotionType.CHARWISE, inclusive=True),
        )

    # Skip through current WORD backwards (non-whitespace) to get before it
    if 0 <= col < len(line) and _is_WORD_char(line[col]):
        while col > 0 and _is_WORD_char(line[col - 1]):
            col -= 1
        col -= 1  # Move to character before the WORD

    # Handle going past start of line
    if col < 0:
        if row > 0:
            row -= 1
            line = lines[row]
            col = len(line) - 1 if line else 0
        else:
            col = 0

    # Skip whitespace backwards
    while 0 <= col < len(line) and line[col].isspace():
        col -= 1
        if col < 0 and row > 0:
            row -= 1
            line = lines[row]
            col = len(line) - 1 if line else 0

    start_pos = Position(row, max(0, col))
    return MotionResult(
        position=start_pos,
        range=Range(start_pos, end_pos, MotionType.CHARWISE, inclusive=True),
    )
