"""Base store class with common JSON file operations."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

LEGACY_CONFIG_DIR = Path.home() / ".sqlit"

# Files that indicate the config directory already holds real user
# config (as opposed to just side-effect cache files created by
# earlier cloud-discovery code that wrote straight into ~/.config/sqlit).
_CORE_CONFIG_FILES = ("settings.json", "connections.json", "credentials.json")


def _has_core_config(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any((path / name).exists() for name in _CORE_CONFIG_FILES)


def _resolve_config_dir() -> Path:
    """Resolve the sqlit config directory, migrating from the legacy path if needed.

    Precedence:
      1. $SQLIT_CONFIG_DIR if set (no migration).
      2. $XDG_CONFIG_HOME/sqlit (falling back to ~/.config/sqlit).

    Migration rules when no env override is set:
      - Legacy ~/.sqlit absent: nothing to do.
      - New path absent: rename the whole legacy tree into place (one
        atomic move on the same filesystem).
      - New path exists but contains no core config files (e.g. only
        cloud-discovery caches): move legacy entries in one-by-one,
        skipping anything already at the destination, then drop the
        empty legacy dir.
      - New path already holds core config: leave legacy alone — the
        user has (knowingly or not) set up the new location and we
        don't want to clobber either side.
    """
    env_override = os.environ.get("SQLIT_CONFIG_DIR")
    if env_override:
        return Path(env_override).expanduser()

    xdg_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg_home).expanduser() if xdg_home else Path.home() / ".config"
    new_path = base / "sqlit"

    legacy = LEGACY_CONFIG_DIR
    if legacy.is_dir() and not _has_core_config(new_path):
        try:
            if not new_path.exists():
                new_path.parent.mkdir(parents=True, exist_ok=True)
                os.rename(legacy, new_path)
            else:
                for entry in legacy.iterdir():
                    dest = new_path / entry.name
                    if dest.exists():
                        continue
                    os.rename(entry, dest)
                try:
                    legacy.rmdir()
                except OSError:
                    pass
        except OSError:
            # e.g. cross-filesystem move. Fall through and let the user
            # migrate manually or point SQLIT_CONFIG_DIR at the legacy path.
            pass

    return new_path


# Shared config directory. Resolved once at import time so module-level
# constants (e.g. CUSTOM_THEME_DIR) pick up the same value.
CONFIG_DIR = _resolve_config_dir()


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
