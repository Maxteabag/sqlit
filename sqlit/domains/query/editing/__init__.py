"""Editing helpers for query text."""

from .deletion import EditResult
from .deletion import delete_all
from .deletion import delete_char
from .deletion import delete_char_back
from .deletion import delete_line
from .deletion import delete_line_end
from .deletion import delete_line_start
from .deletion import delete_to_end
from .deletion import delete_word
from .deletion import delete_word_back
from .deletion import delete_word_end

# Vim motion engine
from .types import MotionResult
from .types import MotionType
from .types import OperatorResult
from .types import Position
from .types import Range

from .clipboard import PasteResult
from .clipboard import get_selection_text
from .clipboard import paste_text
from .clipboard import select_all_range

from .motions import CHAR_MOTIONS
from .motions import MOTIONS

from .operators import OPERATORS
from .operators import operator_change
from .operators import operator_delete
from .operators import operator_yank

from .text_objects import TEXT_OBJECT_CHARS
from .text_objects import get_text_object

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
]
