"""Core types for the vim motion engine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    pass


class MotionType(Enum):
    """Classification of motion types for operator behavior."""

    CHARWISE = auto()  # Character-wise motion (e.g., w, e, f)
    LINEWISE = auto()  # Line-wise motion (e.g., j, k, G)


@dataclass(frozen=True)
class Position:
    """Represents a cursor position in text."""

    row: int
    col: int

    def __lt__(self, other: Position) -> bool:
        if self.row != other.row:
            return self.row < other.row
        return self.col < other.col

    def __le__(self, other: Position) -> bool:
        return self == other or self < other


@dataclass(frozen=True)
class Range:
    """Represents a text range for operations."""

    start: Position
    end: Position
    motion_type: MotionType = MotionType.CHARWISE
    inclusive: bool = False

    def ordered(self) -> Range:
        """Return range with start <= end."""
        if self.end < self.start:
            return Range(self.end, self.start, self.motion_type, self.inclusive)
        return self


@dataclass(frozen=True)
class MotionResult:
    """Result of a motion calculation."""

    position: Position  # Where cursor should end up
    range: Range | None = None  # Range for operator (if applicable)


class MotionFunc(Protocol):
    """Protocol for motion functions."""

    def __call__(
        self, text: str, row: int, col: int, char: str | None = None
    ) -> MotionResult: ...


class TextObjectFunc(Protocol):
    """Protocol for text object functions."""

    def __call__(
        self, text: str, row: int, col: int, around: bool = False
    ) -> Range | None: ...


@dataclass(frozen=True)
class OperatorResult:
    """Result of an operator execution."""

    text: str  # New text content
    row: int  # New cursor row
    col: int  # New cursor column
    yanked: str | None = None  # Deleted/yanked text (for clipboard)
    enter_insert: bool = False  # Whether to enter insert mode (for 'c')
