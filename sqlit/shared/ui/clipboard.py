"""System clipboard helpers.

Terminal clipboard access is platform and terminal dependent. These helpers try
native OS commands first, then pyperclip, and leave terminal-mediated OSC52 to
the caller because Textual owns the active driver.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from importlib import import_module
from typing import Any

CLIPBOARD_TIMEOUT_S = 1.5


def get_system_clipboard_text() -> str:
    """Return text from the system clipboard, or an empty string if unavailable."""
    text = _get_with_native_command()
    if text is not None:
        return text

    try:
        pyperclip = _load_pyperclip()
        return pyperclip.paste() or ""
    except Exception:
        return ""


def copy_to_system_clipboard(text: str) -> bool:
    """Copy text to the system clipboard using the best available backend."""
    if _copy_with_native_command(text):
        return True

    try:
        pyperclip = _load_pyperclip()
        pyperclip.copy(text)
        return True
    except Exception:
        return False


def _load_pyperclip() -> Any:
    return import_module("pyperclip")


def _get_with_native_command() -> str | None:
    if sys.platform == "darwin":
        return _run_text_output_command(["pbpaste"])

    if sys.platform == "win32":
        command = _powershell_command()
        if command:
            return _run_text_output_command(command + ["Get-Clipboard", "-Raw"])
        return None

    for command in _linux_paste_commands():
        text = _run_text_output_command(command)
        if text is not None:
            return text

    return None


def _copy_with_native_command(text: str) -> bool:
    if sys.platform == "darwin":
        return _run_text_input_command(["pbcopy"], text)

    if sys.platform == "win32":
        command = _powershell_command()
        if command and _run_text_input_command(command + ["Set-Clipboard -Value ([Console]::In.ReadToEnd())"], text):
            return True
        return _run_text_input_command(["clip.exe"], text)

    return any(_run_text_input_command(command, text) for command in _linux_copy_commands())


def _linux_paste_commands() -> list[list[str]]:
    commands: list[list[str]] = []
    if os.environ.get("WAYLAND_DISPLAY"):
        commands.append(["wl-paste", "--type", "text"])
    if os.environ.get("DISPLAY"):
        commands.extend(
            [
                ["xclip", "-selection", "clipboard", "-out"],
                ["xsel", "--clipboard", "--output"],
            ]
        )
    if not commands:
        commands.extend(
            [
                ["wl-paste", "--type", "text"],
                ["xclip", "-selection", "clipboard", "-out"],
                ["xsel", "--clipboard", "--output"],
            ]
        )
    return commands


def _linux_copy_commands() -> list[list[str]]:
    commands: list[list[str]] = []
    if os.environ.get("WAYLAND_DISPLAY"):
        commands.append(["wl-copy", "--type", "text/plain"])
    if os.environ.get("DISPLAY"):
        commands.extend(
            [
                ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
            ]
        )
    if not commands:
        commands.extend(
            [
                ["wl-copy", "--type", "text/plain"],
                ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
            ]
        )
    return commands


def _powershell_command() -> list[str] | None:
    for executable in ("pwsh", "powershell.exe", "powershell"):
        if shutil.which(executable):
            return [executable, "-NoProfile", "-NonInteractive", "-Command"]
    return None


def _run_text_output_command(command: list[str]) -> str | None:
    if not shutil.which(command[0]):
        return None
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=CLIPBOARD_TIMEOUT_S,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def _run_text_input_command(command: list[str], text: str) -> bool:
    if not shutil.which(command[0]):
        return False
    try:
        completed = subprocess.run(
            command,
            check=False,
            input=text,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=CLIPBOARD_TIMEOUT_S,
        )
    except Exception:
        return False
    return completed.returncode == 0
