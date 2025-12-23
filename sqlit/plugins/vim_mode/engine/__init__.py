"""Vim emulation engine for sqlit.

This module provides a vim-like editing experience for the query editor,
inspired by prompt_toolkit's vi implementation but adapted for Textual's TextArea.

Architecture:
    VimEngine - Main controller that handles key events
    VimState - Tracks mode, pending operator, registers, etc.
    DocumentWrapper - Adapts TextArea to vim-style operations
    VimKeymapConfig - Configurable key bindings

Usage:
    from sqlit.vim import VimEngine

    engine = VimEngine(text_area)
    engine.set_mode_callback(on_mode_change)

    # In key handler:
    result = engine.handle_key(key)
    if result.consumed:
        event.prevent_default()
"""

from .state import VimMode, VimState, TextObjectType
from .document import DocumentWrapper
from .engine import VimEngine, KeyResult
from .keymap import (
    VimBinding,
    VimKeymapConfig,
    VimKeymapProvider,
    get_vim_keymap,
    set_vim_keymap,
)
from .command import CommandAction, CommandResult, VimCommandHandler

__all__ = [
    # Core
    "VimEngine",
    "VimState",
    "VimMode",
    "KeyResult",
    # Document
    "DocumentWrapper",
    # State types
    "TextObjectType",
    # Keymap
    "VimBinding",
    "VimKeymapConfig",
    "VimKeymapProvider",
    "get_vim_keymap",
    "set_vim_keymap",
    # Command mode
    "CommandAction",
    "CommandResult",
    "VimCommandHandler",
]
