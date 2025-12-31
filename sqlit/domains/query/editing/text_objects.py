"""Text object functions for vim-style selection.

Text objects define regions of text for operators.
'i' prefix = inside (excluding delimiters)
'a' prefix = around (including delimiters)
"""

from __future__ import annotations

from .types import MotionType, Position, Range


def _normalize(text: str, row: int, col: int) -> tuple[list[str], int, int]:
    """Normalize text and cursor position."""
    lines = text.split("\n")
    if not lines:
        lines = [""]
    row = max(0, min(row, len(lines) - 1))
    col = max(0, min(col, len(lines[row])))
    return lines, row, col


def _is_word_char(ch: str) -> bool:
    """Check if character is a word character."""
    return ch.isalnum() or ch == "_"


def _is_WORD_char(ch: str) -> bool:
    """Check if character is a WORD character (non-whitespace)."""
    return not ch.isspace()


# ============================================================================
# Word text objects: iw, aw, iW, aW
# ============================================================================


def text_object_word(
    text: str, row: int, col: int, around: bool = False
) -> Range | None:
    """Select word under cursor (iw/aw)."""
    lines, row, col = _normalize(text, row, col)
    line = lines[row]

    if not line:
        return None

    # Find word boundaries
    start = col
    end = col

    if col < len(line) and _is_word_char(line[col]):
        while start > 0 and _is_word_char(line[start - 1]):
            start -= 1
        while end < len(line) and _is_word_char(line[end]):
            end += 1
    elif col < len(line) and not line[col].isspace():
        # On punctuation
        while (
            start > 0
            and not _is_word_char(line[start - 1])
            and not line[start - 1].isspace()
        ):
            start -= 1
        while (
            end < len(line)
            and not _is_word_char(line[end])
            and not line[end].isspace()
        ):
            end += 1
    else:
        return None

    if around:
        # Include trailing whitespace
        while end < len(line) and line[end].isspace():
            end += 1

    # end-1 because Range is inclusive
    return Range(
        Position(row, start), Position(row, end - 1), MotionType.CHARWISE, inclusive=True
    )


def text_object_WORD(
    text: str, row: int, col: int, around: bool = False
) -> Range | None:
    """Select WORD under cursor (iW/aW)."""
    lines, row, col = _normalize(text, row, col)
    line = lines[row]

    if not line or col >= len(line) or line[col].isspace():
        return None

    start = col
    end = col

    while start > 0 and not line[start - 1].isspace():
        start -= 1
    while end < len(line) and not line[end].isspace():
        end += 1

    if around:
        while end < len(line) and line[end].isspace():
            end += 1

    return Range(
        Position(row, start), Position(row, end - 1), MotionType.CHARWISE, inclusive=True
    )


# ============================================================================
# Quote text objects: i", a", i', a', i`, a`
# ============================================================================


def text_object_quote(
    text: str, row: int, col: int, around: bool = False, quote: str = '"'
) -> Range | None:
    """Select quoted string (i"/a", i'/a', i`/a`)."""
    lines, row, col = _normalize(text, row, col)
    line = lines[row]

    # Find opening and closing quotes
    start = None
    end = None
    in_quote = False
    quote_start = -1

    for i, ch in enumerate(line):
        if ch == quote:
            if not in_quote:
                quote_start = i
                in_quote = True
            else:
                # Found closing quote
                if quote_start <= col <= i or (start is None and i > col):
                    start = quote_start
                    end = i
                    if quote_start <= col <= i:
                        break
                in_quote = False
                quote_start = -1

    if start is None or end is None:
        return None

    if around:
        return Range(
            Position(row, start), Position(row, end), MotionType.CHARWISE, inclusive=True
        )
    else:
        # Inside: exclude the quotes themselves
        if start + 1 > end - 1:
            # Empty quotes
            return Range(
                Position(row, start + 1),
                Position(row, start),
                MotionType.CHARWISE,
                inclusive=True,
            )
        return Range(
            Position(row, start + 1),
            Position(row, end - 1),
            MotionType.CHARWISE,
            inclusive=True,
        )


# ============================================================================
# Bracket text objects: i(, a(, i[, a[, i{, a{
# ============================================================================

BRACKET_PAIRS = {
    "(": ")",
    ")": "(",
    "[": "]",
    "]": "[",
    "{": "}",
    "}": "{",
    "<": ">",
    ">": "<",
}


def text_object_bracket(
    text: str, row: int, col: int, around: bool = False, open_bracket: str = "("
) -> Range | None:
    """Select bracket pair contents (i(/a(, i[/a[, i{/a{)."""
    lines, row, col = _normalize(text, row, col)

    # Normalize to opening bracket
    if open_bracket in ")]}>" and open_bracket in BRACKET_PAIRS:
        open_bracket = BRACKET_PAIRS[open_bracket]

    close_bracket = BRACKET_PAIRS.get(open_bracket, ")")

    # Search backward for opening bracket
    start_row, start_col = row, col
    depth = 0
    found_start = False

    r, c = row, col
    while r >= 0:
        while c >= 0:
            ch = lines[r][c] if c < len(lines[r]) else ""
            if ch == close_bracket:
                depth += 1
            elif ch == open_bracket:
                if depth == 0:
                    start_row, start_col = r, c
                    found_start = True
                    break
                depth -= 1
            c -= 1
        if found_start:
            break
        r -= 1
        if r >= 0:
            c = len(lines[r]) - 1

    if not found_start:
        return None

    # Search forward for closing bracket
    end_row, end_col = row, col
    depth = 0
    found_end = False

    r, c = start_row, start_col
    while r < len(lines):
        while c < len(lines[r]):
            ch = lines[r][c]
            if ch == open_bracket:
                depth += 1
            elif ch == close_bracket:
                depth -= 1
                if depth == 0:
                    end_row, end_col = r, c
                    found_end = True
                    break
            c += 1
        if found_end:
            break
        r += 1
        c = 0

    if not found_end:
        return None

    if around:
        return Range(
            Position(start_row, start_col),
            Position(end_row, end_col),
            MotionType.CHARWISE,
            inclusive=True,
        )
    else:
        # Inside: exclude the brackets themselves
        # Handle multi-line case
        if start_row == end_row:
            if start_col + 1 > end_col - 1:
                # Empty brackets
                return Range(
                    Position(start_row, start_col + 1),
                    Position(start_row, start_col),
                    MotionType.CHARWISE,
                    inclusive=True,
                )
        return Range(
            Position(start_row, start_col + 1),
            Position(end_row, end_col - 1),
            MotionType.CHARWISE,
            inclusive=True,
        )


# ============================================================================
# Text object registry
# ============================================================================

# Map characters to (object_type, argument)
TEXT_OBJECT_CHARS: dict[str, tuple[str, str | None]] = {
    "w": ("word", None),
    "W": ("WORD", None),
    '"': ("quote", '"'),
    "'": ("quote", "'"),
    "`": ("quote", "`"),
    "(": ("bracket", "("),
    ")": ("bracket", "("),
    "b": ("bracket", "("),  # 'b' alias for ()
    "[": ("bracket", "["),
    "]": ("bracket", "["),
    "{": ("bracket", "{"),
    "}": ("bracket", "{"),
    "B": ("bracket", "{"),  # 'B' alias for {}
    "<": ("bracket", "<"),
    ">": ("bracket", "<"),
}


def get_text_object(
    char: str, text: str, row: int, col: int, around: bool
) -> Range | None:
    """Get text object range by character."""
    if char not in TEXT_OBJECT_CHARS:
        return None

    obj_type, arg = TEXT_OBJECT_CHARS[char]

    if obj_type == "word":
        return text_object_word(text, row, col, around)
    elif obj_type == "WORD":
        return text_object_WORD(text, row, col, around)
    elif obj_type == "quote":
        return text_object_quote(text, row, col, around, quote=arg or '"')
    elif obj_type == "bracket":
        return text_object_bracket(text, row, col, around, open_bracket=arg or "(")

    return None
