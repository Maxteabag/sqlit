"""Read a secret (password, connection URL, ...) from stdin.

Used by the `--password-stdin` / `--url-stdin` / `--ssh-password-stdin`
flags so callers can pipe credentials in instead of passing them on the
command line, where they'd be visible to other users via ``ps`` or
``/proc/<pid>/cmdline``.
"""

from __future__ import annotations

import sys
from typing import TextIO


class StdinSecretError(Exception):
    """Raised when a secret can't be read from stdin."""


def read_secret_from_stdin(
    *,
    label: str = "secret",
    stream: TextIO | None = None,
) -> str:
    """Read one line from stdin and strip the trailing newline.

    Refuses to read when stdin is a TTY — there's no plausible
    non-interactive workflow for that, and silently waiting on user
    input would be confusing when the caller intended a piped value.
    Use ``label`` to make the error point at the offending flag (e.g.
    ``password``, ``url``).
    """
    source: TextIO = stream if stream is not None else sys.stdin
    if source.isatty():
        raise StdinSecretError(
            f"Refusing to read {label} from stdin: stdin is a TTY. "
            f"Pipe the value in, e.g. `echo $SECRET | sqlit ... --{label}-stdin`."
        )

    line = source.readline()
    if line == "":
        raise StdinSecretError(f"No {label} received on stdin (EOF).")

    if line.endswith("\r\n"):
        return line[:-2]
    if line.endswith("\n"):
        return line[:-1]
    return line
