"""Vim state management.

Tracks the current mode, pending operator, count prefix, and register.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Any


class VimMode(Enum):
    """Vim editing modes."""

    NORMAL = "NORMAL"
    INSERT = "INSERT"
    VISUAL = "VISUAL"
    VISUAL_LINE = "V-LINE"
    VISUAL_BLOCK = "V-BLOCK"
    COMMAND = "COMMAND"
    REPLACE = "REPLACE"
    OPERATOR_PENDING = "OP-PENDING"


class TextObjectType(Enum):
    """Selection types for text objects."""

    EXCLUSIVE = auto()  # Motion excludes final character
    INCLUSIVE = auto()  # Motion includes final character
    LINEWISE = auto()   # Operates on whole lines
    BLOCK = auto()      # Block/column selection


@dataclass
class TextObject:
    """Represents a text range returned by text object functions.

    Positions are relative to cursor (negative = before, positive = after).
    """

    start: int  # Start offset from cursor
    end: int    # End offset from cursor
    type: TextObjectType = TextObjectType.EXCLUSIVE


@dataclass
class Register:
    """A vim register holding yanked/deleted text."""

    content: str = ""
    linewise: bool = False  # True if content was yanked linewise


@dataclass
class VimState:
    """Tracks all vim editing state.

    This is the central state object that the VimEngine uses to track:
    - Current mode (NORMAL, INSERT, VISUAL, etc.)
    - Pending operator (d, c, y, etc.)
    - Count prefix (e.g., 3 in 3dw)
    - Current register (for yank/delete)
    - Visual selection anchor
    - Macro recording state
    """

    mode: VimMode = VimMode.NORMAL

    # Operator pending state
    pending_operator: str | None = None
    operator_count: int = 1  # Count before operator (e.g., 2 in 2d3w)
    motion_count: int = 1    # Count before motion (e.g., 3 in 2d3w)

    # Input accumulator for building counts/commands
    input_buffer: str = ""

    # Register state (default is unnamed register "")
    current_register: str = "\""
    registers: dict[str, Register] = field(default_factory=lambda: {
        "\"": Register(),  # Unnamed register (default)
        "0": Register(),   # Yank register
        "-": Register(),   # Small delete register
        "+": Register(),   # System clipboard
        "*": Register(),   # Primary selection (same as + on most systems)
    })

    # Visual mode anchor (row, col)
    visual_anchor: tuple[int, int] | None = None

    # Macro state
    recording_macro: str | None = None  # Register being recorded to
    macros: dict[str, list[str]] = field(default_factory=dict)

    # Last search
    last_search: str = ""
    last_search_direction: int = 1  # 1 = forward, -1 = backward

    # Last f/t/F/T motion
    last_char_search: str = ""
    last_char_search_cmd: str = ""  # 'f', 't', 'F', or 'T'

    # Dot repeat state
    last_change: list[str] = field(default_factory=list)
    recording_change: bool = False

    # Insert mode start position (for proper undo grouping)
    insert_start: tuple[int, int] | None = None

    def reset_counts(self) -> None:
        """Reset count accumulators."""
        self.operator_count = 1
        self.motion_count = 1
        self.input_buffer = ""

    def reset_operator(self) -> None:
        """Reset pending operator state."""
        self.pending_operator = None
        self.reset_counts()

    def get_effective_count(self) -> int:
        """Get the combined count (operator_count * motion_count)."""
        return self.operator_count * self.motion_count

    def enter_mode(self, mode: VimMode) -> None:
        """Transition to a new mode with proper cleanup."""
        old_mode = self.mode
        self.mode = mode

        # Clear operator state when leaving operator pending
        if old_mode == VimMode.OPERATOR_PENDING:
            self.reset_operator()

        # Clear visual anchor when leaving visual modes
        if old_mode in (VimMode.VISUAL, VimMode.VISUAL_LINE, VimMode.VISUAL_BLOCK):
            if mode not in (VimMode.VISUAL, VimMode.VISUAL_LINE, VimMode.VISUAL_BLOCK):
                self.visual_anchor = None

        # Reset input buffer on mode change
        self.input_buffer = ""

    def yank_to_register(self, text: str, linewise: bool = False) -> None:
        """Store text in the current register."""
        reg = Register(content=text, linewise=linewise)

        # Always update unnamed register
        self.registers["\""] = reg

        # Update yank register for yanks (not deletes)
        if self.pending_operator == "y":
            self.registers["0"] = reg

        # Update named register if specified
        if self.current_register not in ("\"", "0", "-"):
            self.registers[self.current_register] = reg

        # Reset to default register
        self.current_register = "\""

    def get_register_content(self, register: str | None = None) -> Register:
        """Get content from a register."""
        reg = register or self.current_register
        return self.registers.get(reg, Register())

    def start_visual(self, anchor: tuple[int, int], mode: VimMode = VimMode.VISUAL) -> None:
        """Enter visual mode with anchor at given position."""
        self.visual_anchor = anchor
        self.enter_mode(mode)

    def is_visual_mode(self) -> bool:
        """Check if currently in any visual mode."""
        return self.mode in (VimMode.VISUAL, VimMode.VISUAL_LINE, VimMode.VISUAL_BLOCK)

    def accumulate_digit(self, digit: str) -> bool:
        """Accumulate a digit for count prefix. Returns True if consumed."""
        if digit == "0" and not self.input_buffer:
            # 0 at start is a motion (go to line start), not a count
            return False

        if digit.isdigit():
            self.input_buffer += digit
            return True
        return False

    def consume_count(self) -> int:
        """Consume accumulated count from input buffer."""
        if self.input_buffer:
            try:
                count = int(self.input_buffer)
                self.input_buffer = ""
                return max(1, count)
            except ValueError:
                self.input_buffer = ""
        return 1
