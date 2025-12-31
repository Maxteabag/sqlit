"""Pure motion functions for vim-style navigation.

Each motion function calculates target position and/or range.
They are pure functions that do not modify text.
"""

from __future__ import annotations

from .types import MotionFunc, MotionResult, MotionType, Position, Range


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


# ============================================================================
# Basic motions: h, j, k, l
# ============================================================================


def motion_left(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move cursor left (h)."""
    lines, row, col = _normalize(text, row, col)
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


# ============================================================================
# Word motions: w, W, b, B, e, E
# ============================================================================


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


# ============================================================================
# Line motions: 0, $, G
# ============================================================================


def motion_line_start(
    text: str, row: int, col: int, char: str | None = None
) -> MotionResult:
    """Move to start of line (0)."""
    lines, row, col = _normalize(text, row, col)
    return MotionResult(
        position=Position(row, 0),
        range=Range(
            Position(row, 0),
            Position(row, col),
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


# ============================================================================
# Character search motions: f, F, t, T
# ============================================================================


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
    lines, row, col = _normalize(text, row, col)
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
    lines, row, col = _normalize(text, row, col)
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


# ============================================================================
# Bracket matching: %
# ============================================================================

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


# ============================================================================
# Motion registry
# ============================================================================

MOTIONS: dict[str, MotionFunc] = {
    "h": motion_left,
    "j": motion_down,
    "k": motion_up,
    "l": motion_right,
    "w": motion_word,
    "W": motion_WORD,
    "b": motion_word_back,
    "B": motion_WORD_back,
    "e": motion_word_end,
    "E": motion_WORD_end,
    "0": motion_line_start,
    "$": motion_line_end,
    "G": motion_last_line,
    "f": motion_find_char,  # Requires char argument
    "F": motion_find_char_back,  # Requires char argument
    "t": motion_till_char,  # Requires char argument
    "T": motion_till_char_back,  # Requires char argument
    "%": motion_matching_bracket,
}

# Motions that require a character argument
CHAR_MOTIONS = {"f", "F", "t", "T"}
