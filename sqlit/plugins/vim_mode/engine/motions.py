"""Vim motion functions.

Motions compute cursor destinations without modifying text.
They're used both for navigation and as targets for operators.

Motion functions are registered by name and looked up via the keymap.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from .state import TextObjectType

if TYPE_CHECKING:
    from .document import DocumentWrapper
    from .state import VimState


@dataclass
class MotionResult:
    """Result of a motion computation."""

    position: tuple[int, int]  # Target cursor position (row, col)
    type: TextObjectType = TextObjectType.EXCLUSIVE
    failed: bool = False  # True if motion couldn't be performed


# Type alias for motion functions
MotionFunc = Callable[["DocumentWrapper", "VimState", int], MotionResult]


# ─────────────────────────────────────────────────────────────────
# Basic Cursor Motions (h, j, k, l)
# ─────────────────────────────────────────────────────────────────


def motion_left(doc: DocumentWrapper, state: VimState, count: int) -> MotionResult:
    """Move cursor left (h motion)."""
    pos = doc.get_cursor_left(count)
    return MotionResult(position=pos, type=TextObjectType.EXCLUSIVE)


def motion_right(doc: DocumentWrapper, state: VimState, count: int) -> MotionResult:
    """Move cursor right (l motion)."""
    pos = doc.get_cursor_right(count)
    return MotionResult(position=pos, type=TextObjectType.EXCLUSIVE)


def motion_up(doc: DocumentWrapper, state: VimState, count: int) -> MotionResult:
    """Move cursor up (k motion)."""
    pos = doc.get_cursor_up(count)
    return MotionResult(position=pos, type=TextObjectType.LINEWISE)


def motion_down(doc: DocumentWrapper, state: VimState, count: int) -> MotionResult:
    """Move cursor down (j motion)."""
    pos = doc.get_cursor_down(count)
    return MotionResult(position=pos, type=TextObjectType.LINEWISE)


# ─────────────────────────────────────────────────────────────────
# Line Position Motions (0, ^, $, g_)
# ─────────────────────────────────────────────────────────────────


def motion_line_start(doc: DocumentWrapper, state: VimState, count: int) -> MotionResult:
    """Move to start of line (0 motion)."""
    pos = doc.get_line_start()
    return MotionResult(position=pos, type=TextObjectType.EXCLUSIVE)


def motion_first_non_blank(doc: DocumentWrapper, state: VimState, count: int) -> MotionResult:
    """Move to first non-blank character (^ motion)."""
    pos = doc.get_first_non_blank()
    return MotionResult(position=pos, type=TextObjectType.EXCLUSIVE)


def motion_line_end(doc: DocumentWrapper, state: VimState, count: int) -> MotionResult:
    """Move to end of line ($ motion)."""
    pos = doc.get_line_end()
    return MotionResult(position=pos, type=TextObjectType.INCLUSIVE)


def motion_last_non_blank(doc: DocumentWrapper, state: VimState, count: int) -> MotionResult:
    """Move to last non-blank character (g_ motion)."""
    pos = doc.get_last_non_blank()
    return MotionResult(position=pos, type=TextObjectType.INCLUSIVE)


# ─────────────────────────────────────────────────────────────────
# Word Motions (w, W, e, E, b, B)
# ─────────────────────────────────────────────────────────────────


def motion_word_forward(doc: DocumentWrapper, state: VimState, count: int) -> MotionResult:
    """Move to next word start (w motion)."""
    pos = doc.get_word_start_forward(count, big_word=False)
    return MotionResult(position=pos, type=TextObjectType.EXCLUSIVE)


def motion_word_forward_big(doc: DocumentWrapper, state: VimState, count: int) -> MotionResult:
    """Move to next WORD start (W motion)."""
    pos = doc.get_word_start_forward(count, big_word=True)
    return MotionResult(position=pos, type=TextObjectType.EXCLUSIVE)


def motion_word_end(doc: DocumentWrapper, state: VimState, count: int) -> MotionResult:
    """Move to next word end (e motion)."""
    pos = doc.get_word_end_forward(count, big_word=False)
    return MotionResult(position=pos, type=TextObjectType.INCLUSIVE)


def motion_word_end_big(doc: DocumentWrapper, state: VimState, count: int) -> MotionResult:
    """Move to next WORD end (E motion)."""
    pos = doc.get_word_end_forward(count, big_word=True)
    return MotionResult(position=pos, type=TextObjectType.INCLUSIVE)


def motion_word_backward(doc: DocumentWrapper, state: VimState, count: int) -> MotionResult:
    """Move to previous word start (b motion)."""
    pos = doc.get_word_start_backward(count, big_word=False)
    return MotionResult(position=pos, type=TextObjectType.EXCLUSIVE)


def motion_word_backward_big(doc: DocumentWrapper, state: VimState, count: int) -> MotionResult:
    """Move to previous WORD start (B motion)."""
    pos = doc.get_word_start_backward(count, big_word=True)
    return MotionResult(position=pos, type=TextObjectType.EXCLUSIVE)


# ─────────────────────────────────────────────────────────────────
# Document Position Motions (gg, G, [count]G)
# ─────────────────────────────────────────────────────────────────


def motion_document_start(doc: DocumentWrapper, state: VimState, count: int) -> MotionResult:
    """Move to start of document or line N (gg motion)."""
    if count > 1:
        # [count]gg goes to line N
        pos = doc.get_line_n(count)
    else:
        pos = doc.get_document_start()
    return MotionResult(position=pos, type=TextObjectType.LINEWISE)


def motion_document_end(doc: DocumentWrapper, state: VimState, count: int) -> MotionResult:
    """Move to end of document or line N (G motion)."""
    if count > 1:
        # [count]G goes to line N
        pos = doc.get_line_n(count)
    else:
        pos = doc.get_document_end()
    return MotionResult(position=pos, type=TextObjectType.LINEWISE)


# ─────────────────────────────────────────────────────────────────
# Find Character Motions (f, F, t, T, ;, ,)
# ─────────────────────────────────────────────────────────────────


def motion_find_char(
    doc: DocumentWrapper,
    state: VimState,
    count: int,
    char: str,
    forward: bool = True,
    before: bool = False,
) -> MotionResult:
    """Find character on current line (f/F/t/T motion)."""
    if forward:
        pos = doc.find_char_forward(char, count, before=before)
    else:
        pos = doc.find_char_backward(char, count, before=before)

    if pos is None:
        return MotionResult(
            position=doc.cursor_location,
            type=TextObjectType.EXCLUSIVE,
            failed=True,
        )

    # Store for ; and , repeat
    cmd = "t" if before else "f"
    if not forward:
        cmd = cmd.upper()
    state.last_char_search = char
    state.last_char_search_cmd = cmd

    motion_type = TextObjectType.INCLUSIVE if forward and not before else TextObjectType.EXCLUSIVE
    return MotionResult(position=pos, type=motion_type)


def motion_repeat_find(doc: DocumentWrapper, state: VimState, count: int) -> MotionResult:
    """Repeat last f/F/t/T motion (; motion)."""
    if not state.last_char_search or not state.last_char_search_cmd:
        return MotionResult(position=doc.cursor_location, failed=True)

    cmd = state.last_char_search_cmd
    forward = cmd in "ft"
    before = cmd.lower() == "t"
    char = state.last_char_search

    return motion_find_char(doc, state, count, char, forward=forward, before=before)


def motion_repeat_find_reverse(doc: DocumentWrapper, state: VimState, count: int) -> MotionResult:
    """Repeat last f/F/t/T motion in reverse (, motion)."""
    if not state.last_char_search or not state.last_char_search_cmd:
        return MotionResult(position=doc.cursor_location, failed=True)

    cmd = state.last_char_search_cmd
    # Reverse the direction
    forward = cmd not in "ft"
    before = cmd.lower() == "t"
    char = state.last_char_search

    return motion_find_char(doc, state, count, char, forward=forward, before=before)


# ─────────────────────────────────────────────────────────────────
# Motion Registry - maps handler names from keymap to functions
# ─────────────────────────────────────────────────────────────────

MOTION_HANDLERS: dict[str, MotionFunc] = {
    "motion_left": motion_left,
    "motion_right": motion_right,
    "motion_up": motion_up,
    "motion_down": motion_down,
    "motion_line_start": motion_line_start,
    "motion_first_non_blank": motion_first_non_blank,
    "motion_line_end": motion_line_end,
    "motion_last_non_blank": motion_last_non_blank,
    "motion_word_forward": motion_word_forward,
    "motion_word_forward_big": motion_word_forward_big,
    "motion_word_end": motion_word_end,
    "motion_word_end_big": motion_word_end_big,
    "motion_word_backward": motion_word_backward,
    "motion_word_backward_big": motion_word_backward_big,
    "motion_document_start": motion_document_start,
    "motion_document_end": motion_document_end,
    "motion_repeat_find": motion_repeat_find,
    "motion_repeat_find_reverse": motion_repeat_find_reverse,
}


def get_motion_handler(name: str) -> MotionFunc | None:
    """Get a motion function by handler name."""
    return MOTION_HANDLERS.get(name)
