"""Document wrapper for TextArea.

Provides vim-style navigation and manipulation methods on top of
Textual's TextArea widget, similar to prompt_toolkit's Document class.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from textual.widgets import TextArea


# Word characters for vim's definition of a "word" vs "WORD"
WORD_CHARS = re.compile(r"[a-zA-Z0-9_]")
NON_WORD_CHARS = re.compile(r"[^a-zA-Z0-9_\s]")


class DocumentWrapper:
    """Wraps a TextArea to provide vim-style document operations.

    This class provides methods similar to prompt_toolkit's Document,
    allowing vim motions and text objects to work with Textual's TextArea.
    """

    def __init__(self, text_area: TextArea) -> None:
        self._ta = text_area

    # ─────────────────────────────────────────────────────────────────
    # Properties
    # ─────────────────────────────────────────────────────────────────

    @property
    def text(self) -> str:
        """Full document text."""
        return self._ta.text

    @property
    def lines(self) -> list[str]:
        """Document as list of lines."""
        return self.text.split("\n")

    @property
    def line_count(self) -> int:
        """Number of lines in document."""
        return len(self.lines)

    @property
    def cursor_row(self) -> int:
        """Current cursor row (0-indexed)."""
        return self._ta.cursor_location[0]

    @property
    def cursor_col(self) -> int:
        """Current cursor column (0-indexed)."""
        return self._ta.cursor_location[1]

    @property
    def cursor_location(self) -> tuple[int, int]:
        """Current cursor position as (row, col)."""
        return self._ta.cursor_location

    @property
    def current_line(self) -> str:
        """Text of the current line."""
        lines = self.lines
        if 0 <= self.cursor_row < len(lines):
            return lines[self.cursor_row]
        return ""

    @property
    def current_line_length(self) -> int:
        """Length of current line."""
        return len(self.current_line)

    @property
    def char_at_cursor(self) -> str:
        """Character at cursor position, or empty string if at EOL."""
        line = self.current_line
        col = self.cursor_col
        if 0 <= col < len(line):
            return line[col]
        return ""

    @property
    def char_before_cursor(self) -> str:
        """Character before cursor, or empty string if at start."""
        line = self.current_line
        col = self.cursor_col - 1
        if 0 <= col < len(line):
            return line[col]
        return ""

    @property
    def text_before_cursor(self) -> str:
        """All text before cursor on current line."""
        return self.current_line[: self.cursor_col]

    @property
    def text_after_cursor(self) -> str:
        """All text from cursor to end of current line (inclusive)."""
        return self.current_line[self.cursor_col :]

    @property
    def on_first_line(self) -> bool:
        """True if cursor is on first line."""
        return self.cursor_row == 0

    @property
    def on_last_line(self) -> bool:
        """True if cursor is on last line."""
        return self.cursor_row >= self.line_count - 1

    @property
    def at_line_start(self) -> bool:
        """True if cursor is at start of line."""
        return self.cursor_col == 0

    @property
    def at_line_end(self) -> bool:
        """True if cursor is at or past end of line."""
        return self.cursor_col >= self.current_line_length

    @property
    def at_document_start(self) -> bool:
        """True if cursor is at start of document."""
        return self.cursor_row == 0 and self.cursor_col == 0

    @property
    def at_document_end(self) -> bool:
        """True if cursor is at end of document."""
        return self.on_last_line and self.at_line_end

    # ─────────────────────────────────────────────────────────────────
    # Cursor Movement (returns new position, doesn't move cursor)
    # ─────────────────────────────────────────────────────────────────

    def get_cursor_left(self, count: int = 1) -> tuple[int, int]:
        """Get position after moving left by count chars (stays on line)."""
        new_col = max(0, self.cursor_col - count)
        return (self.cursor_row, new_col)

    def get_cursor_right(self, count: int = 1) -> tuple[int, int]:
        """Get position after moving right by count chars (stays on line)."""
        max_col = max(0, self.current_line_length - 1)  # vim stops before EOL
        new_col = min(max_col, self.cursor_col + count)
        return (self.cursor_row, new_col)

    def get_cursor_up(self, count: int = 1) -> tuple[int, int]:
        """Get position after moving up by count lines."""
        new_row = max(0, self.cursor_row - count)
        # Clamp column to new line length
        new_line_len = len(self.lines[new_row]) if new_row < len(self.lines) else 0
        new_col = min(self.cursor_col, max(0, new_line_len - 1))
        return (new_row, new_col)

    def get_cursor_down(self, count: int = 1) -> tuple[int, int]:
        """Get position after moving down by count lines."""
        new_row = min(self.line_count - 1, self.cursor_row + count)
        # Clamp column to new line length
        new_line_len = len(self.lines[new_row]) if new_row < len(self.lines) else 0
        new_col = min(self.cursor_col, max(0, new_line_len - 1))
        return (new_row, new_col)

    def get_line_start(self) -> tuple[int, int]:
        """Get position at start of current line (0 motion)."""
        return (self.cursor_row, 0)

    def get_line_end(self) -> tuple[int, int]:
        """Get position at end of current line ($ motion)."""
        return (self.cursor_row, max(0, self.current_line_length - 1))

    def get_first_non_blank(self) -> tuple[int, int]:
        """Get position of first non-blank char on line (^ motion)."""
        line = self.current_line
        for i, char in enumerate(line):
            if not char.isspace():
                return (self.cursor_row, i)
        return (self.cursor_row, 0)

    def get_last_non_blank(self) -> tuple[int, int]:
        """Get position of last non-blank char on line (g_ motion)."""
        line = self.current_line.rstrip()
        if line:
            return (self.cursor_row, len(line) - 1)
        return (self.cursor_row, 0)

    def get_document_start(self) -> tuple[int, int]:
        """Get position at start of document (gg motion)."""
        return (0, 0)

    def get_document_end(self) -> tuple[int, int]:
        """Get position at last line (G motion)."""
        last_row = max(0, self.line_count - 1)
        # Go to first non-blank of last line
        lines = self.lines
        if last_row < len(lines):
            line = lines[last_row]
            for i, char in enumerate(line):
                if not char.isspace():
                    return (last_row, i)
        return (last_row, 0)

    def get_line_n(self, n: int) -> tuple[int, int]:
        """Get position at line n (1-indexed, for [count]G)."""
        row = max(0, min(n - 1, self.line_count - 1))
        lines = self.lines
        if row < len(lines):
            line = lines[row]
            for i, char in enumerate(line):
                if not char.isspace():
                    return (row, i)
        return (row, 0)

    # ─────────────────────────────────────────────────────────────────
    # Word Navigation
    # ─────────────────────────────────────────────────────────────────

    def _is_word_char(self, char: str) -> bool:
        """Check if char is a word character (alphanumeric or _)."""
        return bool(WORD_CHARS.match(char))

    def _is_punctuation(self, char: str) -> bool:
        """Check if char is punctuation (not word char, not whitespace)."""
        return bool(NON_WORD_CHARS.match(char))

    def _get_char_class(self, char: str) -> int:
        """Get character class: 0=whitespace, 1=word, 2=punctuation."""
        if char.isspace():
            return 0
        if self._is_word_char(char):
            return 1
        return 2

    def get_word_start_forward(self, count: int = 1, big_word: bool = False) -> tuple[int, int]:
        """Get position of next word start (w/W motion)."""
        row, col = self.cursor_row, self.cursor_col
        lines = self.lines

        for _ in range(count):
            if row >= len(lines):
                break

            line = lines[row]

            # If big_word, only care about whitespace boundaries
            if big_word:
                # Skip current non-whitespace
                while col < len(line) and not line[col].isspace():
                    col += 1
                # Skip whitespace
                while col < len(line) and line[col].isspace():
                    col += 1
                # If at EOL, go to next line
                if col >= len(line):
                    row += 1
                    col = 0
                    if row < len(lines):
                        # Skip leading whitespace on new line
                        while col < len(lines[row]) and lines[row][col].isspace():
                            col += 1
            else:
                # Small word: respect word/punctuation boundaries
                if col < len(line):
                    start_class = self._get_char_class(line[col])
                    # Skip current word class
                    while col < len(line) and self._get_char_class(line[col]) == start_class:
                        col += 1
                # Skip whitespace
                while col < len(line) and line[col].isspace():
                    col += 1
                # If at EOL, go to next line
                if col >= len(line):
                    row += 1
                    col = 0
                    if row < len(lines):
                        # Skip leading whitespace on new line
                        while col < len(lines[row]) and lines[row][col].isspace():
                            col += 1

        return (min(row, len(lines) - 1), col)

    def get_word_end_forward(self, count: int = 1, big_word: bool = False) -> tuple[int, int]:
        """Get position of next word end (e/E motion)."""
        row, col = self.cursor_row, self.cursor_col
        lines = self.lines

        for _ in range(count):
            if row >= len(lines):
                break

            # Move forward at least one char
            col += 1
            line = lines[row] if row < len(lines) else ""

            # Handle EOL
            if col >= len(line):
                row += 1
                col = 0
                if row >= len(lines):
                    break
                line = lines[row]
                # Skip leading whitespace
                while col < len(line) and line[col].isspace():
                    col += 1

            if row >= len(lines) or col >= len(lines[row]):
                break

            line = lines[row]

            if big_word:
                # Skip whitespace first
                while col < len(line) and line[col].isspace():
                    col += 1
                # Go to end of non-whitespace
                while col < len(line) - 1 and not line[col + 1].isspace():
                    col += 1
            else:
                # Skip whitespace
                while col < len(line) and line[col].isspace():
                    col += 1
                if col < len(line):
                    # Go to end of current word class
                    char_class = self._get_char_class(line[col])
                    while col < len(line) - 1 and self._get_char_class(line[col + 1]) == char_class:
                        col += 1

        return (min(row, len(lines) - 1), col)

    def get_word_start_backward(self, count: int = 1, big_word: bool = False) -> tuple[int, int]:
        """Get position of previous word start (b/B motion)."""
        row, col = self.cursor_row, self.cursor_col
        lines = self.lines

        for _ in range(count):
            # Move back at least one char
            col -= 1

            # Handle going to previous line
            if col < 0:
                row -= 1
                if row < 0:
                    return (0, 0)
                col = len(lines[row]) - 1 if row < len(lines) and lines[row] else 0

            if row < 0:
                return (0, 0)

            line = lines[row] if row < len(lines) else ""

            if big_word:
                # Skip whitespace backward
                while col >= 0 and col < len(line) and line[col].isspace():
                    col -= 1
                if col < 0:
                    row -= 1
                    if row < 0:
                        return (0, 0)
                    line = lines[row]
                    col = len(line) - 1

                # Go to start of non-whitespace
                while col > 0 and not line[col - 1].isspace():
                    col -= 1
            else:
                # Skip whitespace backward
                while col >= 0 and col < len(line) and line[col].isspace():
                    col -= 1
                if col < 0:
                    row -= 1
                    if row < 0:
                        return (0, 0)
                    line = lines[row]
                    col = len(line) - 1

                if col >= 0 and col < len(line):
                    # Go to start of current word class
                    char_class = self._get_char_class(line[col])
                    while col > 0 and self._get_char_class(line[col - 1]) == char_class:
                        col -= 1

        return (max(0, row), max(0, col))

    # ─────────────────────────────────────────────────────────────────
    # Find Character (f/F/t/T motions)
    # ─────────────────────────────────────────────────────────────────

    def find_char_forward(
        self, char: str, count: int = 1, before: bool = False
    ) -> tuple[int, int] | None:
        """Find character forward on current line (f/t motion).

        Args:
            char: Character to find
            count: Number of occurrences to skip
            before: If True, stop before the char (t motion)

        Returns:
            New position or None if not found
        """
        line = self.current_line
        col = self.cursor_col + 1
        found = 0

        while col < len(line):
            if line[col] == char:
                found += 1
                if found >= count:
                    if before:
                        col -= 1
                    return (self.cursor_row, col)
            col += 1

        return None

    def find_char_backward(
        self, char: str, count: int = 1, before: bool = False
    ) -> tuple[int, int] | None:
        """Find character backward on current line (F/T motion).

        Args:
            char: Character to find
            count: Number of occurrences to skip
            before: If True, stop after the char (T motion)

        Returns:
            New position or None if not found
        """
        line = self.current_line
        col = self.cursor_col - 1
        found = 0

        while col >= 0:
            if line[col] == char:
                found += 1
                if found >= count:
                    if before:
                        col += 1
                    return (self.cursor_row, col)
            col -= 1

        return None

    # ─────────────────────────────────────────────────────────────────
    # Text Object Boundaries
    # ─────────────────────────────────────────────────────────────────

    def get_word_boundaries(self, big_word: bool = False) -> tuple[int, int]:
        """Get start and end column of word under cursor (iw text object)."""
        line = self.current_line
        col = self.cursor_col

        if not line or col >= len(line):
            return (col, col)

        if big_word:
            # WORD: just non-whitespace
            if line[col].isspace():
                return (col, col)

            start = col
            end = col

            while start > 0 and not line[start - 1].isspace():
                start -= 1
            while end < len(line) - 1 and not line[end + 1].isspace():
                end += 1

            return (start, end + 1)
        else:
            # word: same character class
            char_class = self._get_char_class(line[col])

            start = col
            end = col

            while start > 0 and self._get_char_class(line[start - 1]) == char_class:
                start -= 1
            while end < len(line) - 1 and self._get_char_class(line[end + 1]) == char_class:
                end += 1

            return (start, end + 1)

    def get_outer_word_boundaries(self, big_word: bool = False) -> tuple[int, int]:
        """Get word boundaries including trailing whitespace (aw text object)."""
        start, end = self.get_word_boundaries(big_word)
        line = self.current_line

        # Include trailing whitespace
        while end < len(line) and line[end].isspace():
            end += 1

        # If no trailing whitespace, include leading whitespace
        if end == start + (len(self.current_line[start:end].rstrip())):
            while start > 0 and line[start - 1].isspace():
                start -= 1

        return (start, end)

    def get_quote_boundaries(
        self, quote_char: str, inner: bool = True
    ) -> tuple[tuple[int, int], tuple[int, int]] | None:
        """Get boundaries of quoted string (i"/a" etc. text objects).

        Returns:
            Tuple of ((start_row, start_col), (end_row, end_col)) or None if not found
        """
        line = self.current_line
        col = self.cursor_col

        # Find opening quote (search backward)
        start = col
        while start >= 0 and (start >= len(line) or line[start] != quote_char):
            start -= 1

        if start < 0:
            # Not inside quotes, search forward for opening
            start = col
            while start < len(line) and line[start] != quote_char:
                start += 1
            if start >= len(line):
                return None

        # Find closing quote
        end = start + 1
        while end < len(line) and line[end] != quote_char:
            end += 1

        if end >= len(line):
            return None

        if inner:
            # Exclude quotes
            return ((self.cursor_row, start + 1), (self.cursor_row, end))
        else:
            # Include quotes
            return ((self.cursor_row, start), (self.cursor_row, end + 1))

    def get_bracket_boundaries(
        self, open_char: str, close_char: str, inner: bool = True
    ) -> tuple[tuple[int, int], tuple[int, int]] | None:
        """Get boundaries of bracket pair (i(/a( etc. text objects).

        Returns:
            Tuple of ((start_row, start_col), (end_row, end_col)) or None if not found
        """
        # This is a simplified single-line implementation
        # A full implementation would need to search across lines and handle nesting
        line = self.current_line
        col = self.cursor_col

        # Find opening bracket (search backward, respecting nesting)
        depth = 0
        start = col

        while start >= 0:
            if start < len(line):
                if line[start] == close_char:
                    depth += 1
                elif line[start] == open_char:
                    if depth == 0:
                        break
                    depth -= 1
            start -= 1

        if start < 0:
            return None

        # Find closing bracket (search forward, respecting nesting)
        depth = 0
        end = start + 1

        while end < len(line):
            if line[end] == open_char:
                depth += 1
            elif line[end] == close_char:
                if depth == 0:
                    break
                depth -= 1
            end += 1

        if end >= len(line):
            return None

        if inner:
            return ((self.cursor_row, start + 1), (self.cursor_row, end))
        else:
            return ((self.cursor_row, start), (self.cursor_row, end + 1))

    # ─────────────────────────────────────────────────────────────────
    # Text Manipulation
    # ─────────────────────────────────────────────────────────────────

    def move_cursor(self, pos: tuple[int, int], select: bool = False) -> None:
        """Move cursor to position."""
        self._ta.move_cursor(pos, select=select)

    def set_selection(self, start: tuple[int, int], end: tuple[int, int]) -> None:
        """Set the selection range explicitly.

        Args:
            start: Selection anchor (where selection started)
            end: Selection cursor (where cursor is now)
        """
        from textual.document._document import Selection
        self._ta.selection = Selection(start, end)

    def insert_text(self, text: str) -> None:
        """Insert text at cursor."""
        self._ta.insert(text)

    def delete_range(
        self, start: tuple[int, int], end: tuple[int, int]
    ) -> str:
        """Delete text between start and end positions. Returns deleted text."""
        # Ensure start <= end
        if start > end:
            start, end = end, start

        # Get the text that will be deleted
        deleted = self.get_text_between(start, end)

        # Use TextArea's replace method
        self._ta.replace("", start, end)

        return deleted

    def get_text_between(
        self, start: tuple[int, int], end: tuple[int, int]
    ) -> str:
        """Get text between two positions."""
        if start > end:
            start, end = end, start

        lines = self.lines
        start_row, start_col = start
        end_row, end_col = end

        if start_row == end_row:
            # Same line
            if start_row < len(lines):
                return lines[start_row][start_col:end_col]
            return ""

        # Multiple lines
        result_lines = []

        # First line (from start_col to end)
        if start_row < len(lines):
            result_lines.append(lines[start_row][start_col:])

        # Middle lines (complete)
        for row in range(start_row + 1, end_row):
            if row < len(lines):
                result_lines.append(lines[row])

        # Last line (from start to end_col)
        if end_row < len(lines):
            result_lines.append(lines[end_row][:end_col])

        return "\n".join(result_lines)

    def get_line_range(self, start_row: int, end_row: int) -> str:
        """Get complete lines from start_row to end_row (inclusive)."""
        lines = self.lines
        start_row = max(0, start_row)
        end_row = min(len(lines) - 1, end_row)

        return "\n".join(lines[start_row : end_row + 1])

    def delete_lines(self, start_row: int, end_row: int) -> str:
        """Delete complete lines from start_row to end_row (inclusive)."""
        lines = self.lines
        start_row = max(0, start_row)
        end_row = min(len(lines) - 1, end_row)

        # Get deleted text
        deleted = "\n".join(lines[start_row : end_row + 1])

        # Calculate positions for deletion
        start = (start_row, 0)
        if end_row + 1 < len(lines):
            # Not deleting last line - include the newline
            end = (end_row + 1, 0)
        else:
            # Deleting last line
            if start_row > 0:
                # Include newline from previous line
                start = (start_row - 1, len(lines[start_row - 1]))
            end = (end_row, len(lines[end_row]))

        self._ta.replace("", start, end)

        return deleted

    def replace_text(
        self, start: tuple[int, int], end: tuple[int, int], text: str
    ) -> None:
        """Replace text between positions with new text."""
        if start > end:
            start, end = end, start
        self._ta.replace(text, start, end)
