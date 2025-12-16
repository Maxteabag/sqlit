"""Base store class with common JSON file operations."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

# Shared config directory - can be overridden via environment variable for testing
CONFIG_DIR = Path(os.environ.get("SQLIT_CONFIG_DIR", Path.home() / ".sqlit"))


class JSONFileStore:
    """Base class for JSON file-backed stores.

    Provides common file I/O operations with error handling.
    """

    def __init__(self, file_path: Path):
        self._file_path = file_path

    @property
    def file_path(self) -> Path:
        """Get the store's file path."""
        return self._file_path

    def _ensure_dir(self) -> None:
        """Ensure the config directory exists with secure permissions."""
        dir_path = self._file_path.parent
        dir_path.mkdir(parents=True, exist_ok=True)
        # Set directory to owner-only access (0700)
        try:
            os.chmod(dir_path, 0o700)
        except OSError:
            pass  # Best effort on platforms that don't support chmod

    def _read_json(self) -> Any:
        """Read and parse JSON from file.

        Returns:
            Parsed JSON data, or None if file doesn't exist or is invalid.
        """
        if not self._file_path.exists():
            return None
        try:
            with open(self._file_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, TypeError):
            return None

    def _write_json(self, data: Any) -> None:
        """Write data as JSON to file atomically with secure permissions.

        Uses temp file + rename for atomic writes to prevent data corruption
        on crash/power failure. Sets file permissions to owner-only (0600).

        Args:
            data: Data to serialize and write.
        """
        self._ensure_dir()
        # Create temp file in same directory (required for atomic rename)
        fd, tmp_path = tempfile.mkstemp(
            dir=self._file_path.parent,
            prefix=".tmp_",
            suffix=".json",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            # Set file to owner-only access (0600) before making visible
            os.chmod(tmp_path, 0o600)
            # Atomic rename (on POSIX systems)
            os.replace(tmp_path, self._file_path)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def exists(self) -> bool:
        """Check if the store file exists."""
        return self._file_path.exists()
