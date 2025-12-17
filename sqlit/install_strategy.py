"""Detection for how sqlit-tui should suggest/install optional Python drivers.

This module intentionally avoids depending on Textual or other app layers so it
can be used from adapters, services, and UI screens.
"""

from __future__ import annotations

import importlib.util
import os
import site
import sys
import sysconfig
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InstallStrategy:
    """Represents how to install optional Python dependencies for the running app."""

    kind: str
    can_auto_install: bool
    manual_instructions: str
    auto_install_command: list[str] | None = None
    reason_unavailable: str | None = None


def _in_venv() -> bool:
    if os.environ.get("VIRTUAL_ENV"):
        return True
    base_prefix = getattr(sys, "base_prefix", sys.prefix)
    return sys.prefix != base_prefix


def _is_pipx() -> bool:
    pipx_override = os.environ.get("SQLIT_MOCK_PIPX", "").strip().lower()
    if pipx_override in {"1", "true", "yes", "pipx"}:
        return True
    if pipx_override in {"0", "false", "no", "pip"}:
        return False

    exe = sys.executable.lower()
    return "pipx" in exe or "/pipx/venvs/" in exe or "\\pipx\\venvs\\" in exe


def _pep668_externally_managed() -> bool:
    if _in_venv():
        return False

    candidates: list[str] = []
    for key in ("stdlib", "platstdlib"):
        try:
            value = sysconfig.get_path(key)
        except Exception:
            value = None
        if value:
            candidates.append(value)

    for stdlib_path in candidates:
        marker = Path(stdlib_path) / "EXTERNALLY-MANAGED"
        if marker.exists():
            return True
    return False


def _pip_available() -> bool:
    return importlib.util.find_spec("pip") is not None


def _user_site_enabled() -> bool:
    # site.ENABLE_USER_SITE already accounts for PYTHONNOUSERSITE and -s/-S in most cases.
    try:
        return bool(site.ENABLE_USER_SITE)
    except Exception:
        return False


def _install_paths_writable() -> bool:
    try:
        paths = sysconfig.get_paths()
    except Exception:
        return False

    for key in ("purelib", "platlib"):
        value = paths.get(key)
        if not value:
            continue
        path = Path(value)
        # If the directory doesn't exist, check whether we can create it under its parent.
        probe = path if path.exists() else path.parent
        if probe.exists() and os.access(probe, os.W_OK):
            return True
    return False


def detect_strategy(*, extra_name: str, package_name: str) -> InstallStrategy:
    """Detect the best installation strategy for optional driver dependencies."""
    if _is_pipx():
        cmd = ["pipx", "inject", "sqlit-tui", package_name]
        return InstallStrategy(
            kind="pipx",
            can_auto_install=True,
            manual_instructions="pipx inject sqlit-tui " + package_name,
            auto_install_command=cmd,
        )

    if _pep668_externally_managed():
        return InstallStrategy(
            kind="externally-managed",
            can_auto_install=False,
            manual_instructions=(
                "This Python environment is externally managed (PEP 668).\n"
                "Install the driver via your OS package manager, or install sqlit-tui in an isolated environment.\n\n"
                f"pipx install 'sqlit-tui[{extra_name}]'\n"
                f"pipx inject sqlit-tui {package_name}\n"
            ).rstrip(),
            reason_unavailable="Externally managed Python environment (PEP 668).",
        )

    if not _pip_available():
        return InstallStrategy(
            kind="no-pip",
            can_auto_install=False,
            manual_instructions=(
                "pip is not available for this Python interpreter.\n"
                "Install the driver via your OS package manager, or install sqlit-tui in an isolated environment."
            ),
            reason_unavailable="pip is not available.",
        )

    pip_cmd = [sys.executable, "-m", "pip", "install"]
    if _in_venv() or _install_paths_writable():
        cmd = [*pip_cmd, package_name]
        return InstallStrategy(
            kind="pip",
            can_auto_install=True,
            manual_instructions=f"{sys.executable} -m pip install {package_name}",
            auto_install_command=cmd,
        )

    if _user_site_enabled():
        cmd = [*pip_cmd, "--user", package_name]
        return InstallStrategy(
            kind="pip-user",
            can_auto_install=True,
            manual_instructions=f"{sys.executable} -m pip install --user {package_name}",
            auto_install_command=cmd,
        )

    return InstallStrategy(
        kind="pip-unwritable",
        can_auto_install=False,
        manual_instructions=(
            "This Python environment is not writable and user-site installs are disabled.\n"
            "Install the driver via your OS package manager, or use a virtual environment/pipx."
        ),
        reason_unavailable="Python environment not writable and user-site disabled.",
    )
