"""Vim-like editor modes (UI-agnostic)."""

from __future__ import annotations

from enum import Enum


class VimMode(Enum):
    """Vim editing modes."""

    NORMAL = "NORMAL"
    INSERT = "INSERT"
