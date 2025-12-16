"""Terminal detection and command execution utilities."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from enum import Enum


class TerminalType(Enum):
    GNOME = "gnome-terminal"
    KONSOLE = "konsole"
    XTERM = "xterm"
    MACOS = "macos"
    WINDOWS = "windows"
    NONE = "none"


@dataclass
class TerminalResult:
    success: bool
    terminal: TerminalType
    error: str | None = None


def detect_terminal() -> TerminalType:
    """Detect available terminal emulator."""
    if shutil.which("gnome-terminal"):
        return TerminalType.GNOME
    if shutil.which("konsole"):
        return TerminalType.KONSOLE
    if shutil.which("xterm"):
        return TerminalType.XTERM
    if shutil.which("open") and os.uname().sysname == "Darwin":
        return TerminalType.MACOS
    if os.name == "nt":
        return TerminalType.WINDOWS
    return TerminalType.NONE


def run_in_terminal(commands: list[str], wait_message: str = "Press Enter to close...") -> TerminalResult:
    """Run commands in a new terminal window.

    Returns TerminalResult indicating success/failure and which terminal was used.
    """
    terminal = detect_terminal()
    full_command = " && ".join(commands)
    suffix = f'echo ""; echo "{wait_message}"; read'

    try:
        if terminal == TerminalType.GNOME:
            subprocess.Popen(["gnome-terminal", "--", "bash", "-c", f"{full_command}; {suffix}"])
        elif terminal == TerminalType.KONSOLE:
            subprocess.Popen(["konsole", "-e", "bash", "-c", f"{full_command}; {suffix}"])
        elif terminal == TerminalType.XTERM:
            subprocess.Popen(["xterm", "-e", "bash", "-c", f"{full_command}; {suffix}"])
        elif terminal == TerminalType.MACOS:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
                f.write("#!/bin/bash\n")
                f.write(full_command + "\n")
                f.write(f'echo ""\necho "{wait_message}"\nread\n')
                script_path = f.name
            os.chmod(script_path, 0o755)
            subprocess.Popen(["open", "-a", "Terminal", script_path])
        elif terminal == TerminalType.WINDOWS:
            subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", full_command], shell=True)
        else:
            return TerminalResult(success=False, terminal=terminal, error="No terminal emulator found")

        return TerminalResult(success=True, terminal=terminal)

    except Exception as e:
        return TerminalResult(success=False, terminal=terminal, error=str(e))
