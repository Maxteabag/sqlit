"""Vim keymap configuration.

Defines all vim key bindings in a configurable way, similar to sqlit's
main keymap system but handling vim-specific concepts like:
- Motions (can be used standalone or as operator targets)
- Operators (wait for motion/text object)
- Text objects (two-char sequences like iw, aw)
- Multi-char motions (gg, g_, etc.)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Any


class BindingType(Enum):
    """Type of vim key binding."""

    MOTION = auto()          # Movement command (h, j, w, etc.)
    OPERATOR = auto()        # Operates on range (d, c, y, etc.)
    TEXT_OBJECT = auto()     # Text object (iw, aw, i", etc.)
    ACTION = auto()          # Immediate action (i, a, o, p, u, etc.)
    MODE_SWITCH = auto()     # Mode change (v, V, :, etc.)
    PENDING = auto()         # Waits for next char (f, t, r, etc.)


@dataclass
class VimBinding:
    """Definition of a vim key binding."""

    key: str                          # Key or key sequence (e.g., "w", "gg", "iw")
    type: BindingType                 # Type of binding
    handler: str                      # Handler function name
    description: str = ""             # Human-readable description
    modes: tuple[str, ...] = ("normal",)  # Which modes this applies to
    inclusive: bool = False           # For motions: is target included?
    linewise: bool = False            # For motions: operates on lines?


@dataclass
class VimKeymapConfig:
    """Configuration for vim keybindings.

    This can eventually be loaded from JSON/YAML for customization.
    """

    # ─────────────────────────────────────────────────────────────────
    # Motions - cursor movement commands
    # ─────────────────────────────────────────────────────────────────
    motions: dict[str, VimBinding] = field(default_factory=lambda: {
        # Basic cursor movement
        "h": VimBinding("h", BindingType.MOTION, "motion_left", "Left"),
        "l": VimBinding("l", BindingType.MOTION, "motion_right", "Right"),
        "j": VimBinding("j", BindingType.MOTION, "motion_down", "Down", linewise=True),
        "k": VimBinding("k", BindingType.MOTION, "motion_up", "Up", linewise=True),
        "left": VimBinding("left", BindingType.MOTION, "motion_left", "Left"),
        "right": VimBinding("right", BindingType.MOTION, "motion_right", "Right"),
        "down": VimBinding("down", BindingType.MOTION, "motion_down", "Down", linewise=True),
        "up": VimBinding("up", BindingType.MOTION, "motion_up", "Up", linewise=True),
        "backspace": VimBinding("backspace", BindingType.MOTION, "motion_left", "Left"),
        "space": VimBinding("space", BindingType.MOTION, "motion_right", "Right"),

        # Line position
        "0": VimBinding("0", BindingType.MOTION, "motion_line_start", "Line start"),
        "^": VimBinding("^", BindingType.MOTION, "motion_first_non_blank", "First non-blank"),
        "$": VimBinding("$", BindingType.MOTION, "motion_line_end", "Line end", inclusive=True),
        "g_": VimBinding("g_", BindingType.MOTION, "motion_last_non_blank", "Last non-blank", inclusive=True),

        # Word motions
        "w": VimBinding("w", BindingType.MOTION, "motion_word_forward", "Next word"),
        "W": VimBinding("W", BindingType.MOTION, "motion_word_forward_big", "Next WORD"),
        "e": VimBinding("e", BindingType.MOTION, "motion_word_end", "Word end", inclusive=True),
        "E": VimBinding("E", BindingType.MOTION, "motion_word_end_big", "WORD end", inclusive=True),
        "b": VimBinding("b", BindingType.MOTION, "motion_word_backward", "Previous word"),
        "B": VimBinding("B", BindingType.MOTION, "motion_word_backward_big", "Previous WORD"),

        # Document position
        "gg": VimBinding("gg", BindingType.MOTION, "motion_document_start", "Document start", linewise=True),
        "G": VimBinding("G", BindingType.MOTION, "motion_document_end", "Document end", linewise=True),

        # Find char repeat
        ";": VimBinding(";", BindingType.MOTION, "motion_repeat_find", "Repeat f/t"),
        ",": VimBinding(",", BindingType.MOTION, "motion_repeat_find_reverse", "Repeat f/t reverse"),
    })

    # ─────────────────────────────────────────────────────────────────
    # Operators - commands that operate on a range
    # ─────────────────────────────────────────────────────────────────
    operators: dict[str, VimBinding] = field(default_factory=lambda: {
        "d": VimBinding("d", BindingType.OPERATOR, "operator_delete", "Delete"),
        "c": VimBinding("c", BindingType.OPERATOR, "operator_change", "Change"),
        "y": VimBinding("y", BindingType.OPERATOR, "operator_yank", "Yank"),
        ">": VimBinding(">", BindingType.OPERATOR, "operator_indent", "Indent"),
        "<": VimBinding("<", BindingType.OPERATOR, "operator_dedent", "Dedent"),
        "gu": VimBinding("gu", BindingType.OPERATOR, "operator_lowercase", "Lowercase"),
        "gU": VimBinding("gU", BindingType.OPERATOR, "operator_uppercase", "Uppercase"),
        "g~": VimBinding("g~", BindingType.OPERATOR, "operator_swap_case", "Swap case"),
    })

    # ─────────────────────────────────────────────────────────────────
    # Text Objects - selections for operators
    # ─────────────────────────────────────────────────────────────────
    text_objects: dict[str, VimBinding] = field(default_factory=lambda: {
        # Word objects
        "iw": VimBinding("iw", BindingType.TEXT_OBJECT, "textobj_inner_word", "Inner word"),
        "aw": VimBinding("aw", BindingType.TEXT_OBJECT, "textobj_outer_word", "A word"),
        "iW": VimBinding("iW", BindingType.TEXT_OBJECT, "textobj_inner_word_big", "Inner WORD"),
        "aW": VimBinding("aW", BindingType.TEXT_OBJECT, "textobj_outer_word_big", "A WORD"),

        # Quote objects
        'i"': VimBinding('i"', BindingType.TEXT_OBJECT, "textobj_inner_double_quote", 'Inner "..."'),
        'a"': VimBinding('a"', BindingType.TEXT_OBJECT, "textobj_outer_double_quote", 'A "..."'),
        "i'": VimBinding("i'", BindingType.TEXT_OBJECT, "textobj_inner_single_quote", "Inner '...'"),
        "a'": VimBinding("a'", BindingType.TEXT_OBJECT, "textobj_outer_single_quote", "A '...'"),
        "i`": VimBinding("i`", BindingType.TEXT_OBJECT, "textobj_inner_backtick", "Inner `...`"),
        "a`": VimBinding("a`", BindingType.TEXT_OBJECT, "textobj_outer_backtick", "A `...`"),

        # Bracket objects
        "i(": VimBinding("i(", BindingType.TEXT_OBJECT, "textobj_inner_paren", "Inner (...)"),
        "a(": VimBinding("a(", BindingType.TEXT_OBJECT, "textobj_outer_paren", "A (...)"),
        "ib": VimBinding("ib", BindingType.TEXT_OBJECT, "textobj_inner_paren", "Inner (...)"),  # Alias
        "ab": VimBinding("ab", BindingType.TEXT_OBJECT, "textobj_outer_paren", "A (...)"),      # Alias
        "i)": VimBinding("i)", BindingType.TEXT_OBJECT, "textobj_inner_paren", "Inner (...)"),  # Alias
        "a)": VimBinding("a)", BindingType.TEXT_OBJECT, "textobj_outer_paren", "A (...)"),      # Alias

        "i[": VimBinding("i[", BindingType.TEXT_OBJECT, "textobj_inner_bracket", "Inner [...]"),
        "a[": VimBinding("a[", BindingType.TEXT_OBJECT, "textobj_outer_bracket", "A [...]"),
        "i]": VimBinding("i]", BindingType.TEXT_OBJECT, "textobj_inner_bracket", "Inner [...]"),
        "a]": VimBinding("a]", BindingType.TEXT_OBJECT, "textobj_outer_bracket", "A [...]"),

        "i{": VimBinding("i{", BindingType.TEXT_OBJECT, "textobj_inner_brace", "Inner {...}"),
        "a{": VimBinding("a{", BindingType.TEXT_OBJECT, "textobj_outer_brace", "A {...}"),
        "iB": VimBinding("iB", BindingType.TEXT_OBJECT, "textobj_inner_brace", "Inner {...}"),  # Alias
        "aB": VimBinding("aB", BindingType.TEXT_OBJECT, "textobj_outer_brace", "A {...}"),      # Alias
        "i}": VimBinding("i}", BindingType.TEXT_OBJECT, "textobj_inner_brace", "Inner {...}"),
        "a}": VimBinding("a}", BindingType.TEXT_OBJECT, "textobj_outer_brace", "A {...}"),

        "i<": VimBinding("i<", BindingType.TEXT_OBJECT, "textobj_inner_angle", "Inner <...>"),
        "a<": VimBinding("a<", BindingType.TEXT_OBJECT, "textobj_outer_angle", "A <...>"),
        "i>": VimBinding("i>", BindingType.TEXT_OBJECT, "textobj_inner_angle", "Inner <...>"),
        "a>": VimBinding("a>", BindingType.TEXT_OBJECT, "textobj_outer_angle", "A <...>"),
    })

    # ─────────────────────────────────────────────────────────────────
    # Actions - immediate commands
    # ─────────────────────────────────────────────────────────────────
    actions: dict[str, VimBinding] = field(default_factory=lambda: {
        # Insert mode entry
        "i": VimBinding("i", BindingType.ACTION, "action_insert", "Insert", modes=("normal",)),
        "I": VimBinding("I", BindingType.ACTION, "action_insert_line_start", "Insert at line start", modes=("normal",)),
        "a": VimBinding("a", BindingType.ACTION, "action_append", "Append", modes=("normal",)),
        "A": VimBinding("A", BindingType.ACTION, "action_append_line_end", "Append at line end", modes=("normal",)),
        "o": VimBinding("o", BindingType.ACTION, "action_open_below", "Open line below", modes=("normal",)),
        "O": VimBinding("O", BindingType.ACTION, "action_open_above", "Open line above", modes=("normal",)),
        "s": VimBinding("s", BindingType.ACTION, "action_substitute", "Substitute char", modes=("normal",)),
        "S": VimBinding("S", BindingType.ACTION, "action_substitute_line", "Substitute line", modes=("normal",)),
        "C": VimBinding("C", BindingType.ACTION, "action_change_to_eol", "Change to EOL", modes=("normal",)),
        "D": VimBinding("D", BindingType.ACTION, "action_delete_to_eol", "Delete to EOL", modes=("normal",)),

        # Undo/redo
        "u": VimBinding("u", BindingType.ACTION, "action_undo", "Undo", modes=("normal",)),
        "ctrl+r": VimBinding("ctrl+r", BindingType.ACTION, "action_redo", "Redo", modes=("normal",)),

        # Paste
        "p": VimBinding("p", BindingType.ACTION, "action_paste_after", "Paste after", modes=("normal",)),
        "P": VimBinding("P", BindingType.ACTION, "action_paste_before", "Paste before", modes=("normal",)),

        # Other
        "x": VimBinding("x", BindingType.ACTION, "action_delete_char", "Delete char", modes=("normal",)),
        "X": VimBinding("X", BindingType.ACTION, "action_delete_char_before", "Delete char before", modes=("normal",)),
        "~": VimBinding("~", BindingType.ACTION, "action_swap_case_char", "Swap case", modes=("normal",)),
        "J": VimBinding("J", BindingType.ACTION, "action_join_lines", "Join lines", modes=("normal",)),
        ".": VimBinding(".", BindingType.ACTION, "action_repeat", "Repeat last change", modes=("normal",)),

        # Exit insert mode
        "escape": VimBinding("escape", BindingType.ACTION, "action_escape", "Normal mode", modes=("insert", "visual", "command")),
        "ctrl+[": VimBinding("ctrl+[", BindingType.ACTION, "action_escape", "Normal mode", modes=("insert", "visual", "command")),
        "ctrl+c": VimBinding("ctrl+c", BindingType.ACTION, "action_escape", "Normal mode", modes=("insert", "visual", "command")),

    })

    # ─────────────────────────────────────────────────────────────────
    # Visual mode specific actions (i/a behave differently in visual)
    # ─────────────────────────────────────────────────────────────────
    visual_actions: dict[str, VimBinding] = field(default_factory=lambda: {
        "i": VimBinding("i", BindingType.ACTION, "action_visual_insert", "Insert at selection start", modes=("visual",)),
        "a": VimBinding("a", BindingType.ACTION, "action_visual_append", "Append after selection", modes=("visual",)),
        "I": VimBinding("I", BindingType.ACTION, "action_visual_insert", "Insert at selection start", modes=("visual",)),
        "A": VimBinding("A", BindingType.ACTION, "action_visual_append", "Append after selection", modes=("visual",)),
    })

    # ─────────────────────────────────────────────────────────────────
    # Mode switches
    # ─────────────────────────────────────────────────────────────────
    mode_switches: dict[str, VimBinding] = field(default_factory=lambda: {
        "v": VimBinding("v", BindingType.MODE_SWITCH, "mode_visual", "Visual mode", modes=("normal",)),
        "V": VimBinding("V", BindingType.MODE_SWITCH, "mode_visual_line", "Visual line mode", modes=("normal",)),
        "ctrl+v": VimBinding("ctrl+v", BindingType.MODE_SWITCH, "mode_visual_block", "Visual block mode", modes=("normal",)),
        ":": VimBinding(":", BindingType.MODE_SWITCH, "mode_command", "Command mode", modes=("normal", "visual")),
    })

    # ─────────────────────────────────────────────────────────────────
    # Pending commands (wait for next char)
    # ─────────────────────────────────────────────────────────────────
    pending: dict[str, VimBinding] = field(default_factory=lambda: {
        "f": VimBinding("f", BindingType.PENDING, "pending_find_forward", "Find forward"),
        "F": VimBinding("F", BindingType.PENDING, "pending_find_backward", "Find backward"),
        "t": VimBinding("t", BindingType.PENDING, "pending_till_forward", "Till forward"),
        "T": VimBinding("T", BindingType.PENDING, "pending_till_backward", "Till backward"),
        "r": VimBinding("r", BindingType.PENDING, "pending_replace_char", "Replace char", modes=("normal",)),
        '"': VimBinding('"', BindingType.PENDING, "pending_register", "Select register", modes=("normal",)),
    })


class VimKeymapProvider(ABC):
    """Abstract base class for vim keymap providers."""

    @abstractmethod
    def get_config(self) -> VimKeymapConfig:
        """Get the keymap configuration."""
        pass

    def get_motion(self, key: str) -> VimBinding | None:
        """Get motion binding for a key."""
        return self.get_config().motions.get(key)

    def get_operator(self, key: str) -> VimBinding | None:
        """Get operator binding for a key."""
        return self.get_config().operators.get(key)

    def get_text_object(self, key: str) -> VimBinding | None:
        """Get text object binding for a key sequence."""
        return self.get_config().text_objects.get(key)

    def get_action(self, key: str) -> VimBinding | None:
        """Get action binding for a key."""
        return self.get_config().actions.get(key)

    def get_mode_switch(self, key: str) -> VimBinding | None:
        """Get mode switch binding for a key."""
        return self.get_config().mode_switches.get(key)

    def get_pending(self, key: str) -> VimBinding | None:
        """Get pending command binding for a key."""
        return self.get_config().pending.get(key)

    def get_visual_action(self, key: str) -> VimBinding | None:
        """Get visual mode action binding for a key."""
        return self.get_config().visual_actions.get(key)

    def lookup(self, key: str, mode: str = "normal") -> VimBinding | None:
        """Look up any binding for a key in the given mode."""
        config = self.get_config()

        # Check each category
        for bindings in [
            config.motions,
            config.operators,
            config.actions,
            config.mode_switches,
            config.pending,
        ]:
            if key in bindings:
                binding = bindings[key]
                if mode in binding.modes or not binding.modes:
                    return binding

        return None

    def is_motion(self, key: str) -> bool:
        """Check if key is a motion."""
        return key in self.get_config().motions

    def is_operator(self, key: str) -> bool:
        """Check if key is an operator."""
        return key in self.get_config().operators

    def is_text_object_start(self, key: str) -> bool:
        """Check if key starts a text object (i or a)."""
        return key in ("i", "a")

    def get_text_object_keys(self) -> set[str]:
        """Get all text object second characters."""
        objects = self.get_config().text_objects
        # Extract the second char from "iw", "aw", etc.
        return {k[1] for k in objects.keys() if len(k) == 2}


class DefaultVimKeymapProvider(VimKeymapProvider):
    """Default vim keymap with standard bindings."""

    def __init__(self) -> None:
        self._config = VimKeymapConfig()

    def get_config(self) -> VimKeymapConfig:
        return self._config


# Global vim keymap instance
_vim_keymap_provider: VimKeymapProvider | None = None


def get_vim_keymap() -> VimKeymapProvider:
    """Get the current vim keymap provider."""
    global _vim_keymap_provider
    if _vim_keymap_provider is None:
        _vim_keymap_provider = DefaultVimKeymapProvider()
    return _vim_keymap_provider


def set_vim_keymap(provider: VimKeymapProvider) -> None:
    """Set the vim keymap provider (for testing or custom keymaps)."""
    global _vim_keymap_provider
    _vim_keymap_provider = provider


def reset_vim_keymap() -> None:
    """Reset to default vim keymap provider."""
    global _vim_keymap_provider
    _vim_keymap_provider = None
