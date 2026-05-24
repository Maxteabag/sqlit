"""Run a shell command to retrieve a password."""

from __future__ import annotations

import subprocess


class PasswordCommandError(Exception):
    """Raised when a password command fails."""


def run_password_command(command: str, *, timeout: int = 30) -> str:
    """Run a shell command and return its stripped stdout as the password."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise PasswordCommandError(f"Command not found: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise PasswordCommandError(
            f"Password command timed out after {timeout}s: {command}"
        ) from exc

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise PasswordCommandError(
            f"Password command failed (exit {result.returncode}): {stderr}"
        )

    return result.stdout.strip()
