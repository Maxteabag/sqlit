"""Detect terminal editors and resolve the user's editor preference."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass


# Terminal editors we know about, ordered by typical preference.
# The order is what surfaces in the picker top-down.
_KNOWN_EDITORS: tuple[tuple[str, str], ...] = (
    ("nvim", "Neovim"),
    ("vim", "Vim"),
    ("hx", "Helix"),
    ("kak", "Kakoune"),
    ("micro", "Micro"),
    ("nano", "Nano"),
    ("emacs", "Emacs"),
    ("vi", "Vi"),
)


@dataclass(frozen=True)
class EditorEntry:
    """A terminal editor candidate."""

    command: str
    display_name: str
    path: str | None  # None when the binary isn't on PATH.

    @property
    def is_installed(self) -> bool:
        return self.path is not None


def detect_editors() -> list[EditorEntry]:
    """Return all known editors, with each entry's resolved path or None."""
    return [
        EditorEntry(command=cmd, display_name=name, path=shutil.which(cmd))
        for cmd, name in _KNOWN_EDITORS
    ]


def env_default_editor() -> str | None:
    """Return the first usable editor command from $VISUAL or $EDITOR."""
    for var in ("VISUAL", "EDITOR"):
        value = os.environ.get(var, "").strip()
        if not value:
            continue
        # $EDITOR can include args (e.g. "code -w"). Take the binary.
        cmd = value.split()[0]
        if shutil.which(cmd):
            return cmd
    return None


def resolve_editor(preferred: str | None) -> str | None:
    """Pick the editor to use: preferred (if installed) else $VISUAL/$EDITOR."""
    if preferred and shutil.which(preferred):
        return preferred
    return env_default_editor()


def build_editor_argv(editor_cmd: str) -> list[str]:
    """Build the argv prefix for invoking the editor on a file.

    `emacs` is special-cased to use `-nw` so it stays in the terminal.
    """
    if editor_cmd == "emacs":
        return ["emacs", "-nw"]
    return [editor_cmd]
