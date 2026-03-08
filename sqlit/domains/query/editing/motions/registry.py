"""Motion registry and bindings."""

from __future__ import annotations

from ..types import MotionFunc
from .basic import motion_down, motion_left, motion_right, motion_up
from .brackets import motion_matching_bracket
from .lines import (
    motion_current_line,
    motion_first_line,
    motion_last_line,
    motion_line_end,
    motion_line_start,
)
from .search import (
    motion_find_char,
    motion_find_char_back,
    motion_till_char,
    motion_till_char_back,
)
from .words import (
    motion_WORD,
    motion_word,
    motion_WORD_back,
    motion_word_back,
    motion_WORD_end,
    motion_word_end,
    motion_WORD_end_back,
    motion_word_end_back,
)

# Motion registry
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
    "gg": motion_first_line,  # Go to first line
    "ge": motion_word_end_back,  # End of previous word
    "gE": motion_WORD_end_back,  # End of previous WORD
    "_": motion_current_line,  # Current line (dd, yy, cc)
    "f": motion_find_char,  # Requires char argument
    "F": motion_find_char_back,  # Requires char argument
    "t": motion_till_char,  # Requires char argument
    "T": motion_till_char_back,  # Requires char argument
    "%": motion_matching_bracket,
}

# Motions that require a character argument
CHAR_MOTIONS = {"f", "F", "t", "T"}
