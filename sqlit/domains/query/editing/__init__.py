"""Editing helpers for query text."""

from .clipboard import PasteResult, get_selection_text, paste_text, select_all_range
from .deletion import (
    EditResult,
    delete_all,
    delete_char,
    delete_char_back,
    delete_line,
    delete_line_end,
    delete_line_start,
    delete_to_end,
    delete_word,
    delete_word_back,
    delete_word_end,
)
from .motions import CHAR_MOTIONS, MOTIONS
from .operators import OPERATORS, operator_change, operator_delete, operator_yank
from .text_objects import TEXT_OBJECT_CHARS, get_text_object

# Vim motion engine
from .types import MotionResult, MotionType, OperatorResult, Position, Range
from .undo_history import UndoHistory, UndoState
from .comments import toggle_comment_lines

__all__ = [
    # Deletion
    "EditResult",
    "delete_all",
    "delete_char",
    "delete_char_back",
    "delete_line",
    "delete_line_end",
    "delete_line_start",
    "delete_to_end",
    "delete_word",
    "delete_word_back",
    "delete_word_end",
    # Types
    "MotionResult",
    "MotionType",
    "OperatorResult",
    "Position",
    "Range",
    # Clipboard
    "PasteResult",
    "get_selection_text",
    "paste_text",
    "select_all_range",
    # Motions
    "CHAR_MOTIONS",
    "MOTIONS",
    # Operators
    "OPERATORS",
    "operator_change",
    "operator_delete",
    "operator_yank",
    # Text objects
    "TEXT_OBJECT_CHARS",
    "get_text_object",
    # Undo/redo
    "UndoHistory",
    "UndoState",
    # Comments
    "toggle_comment_lines",
]
