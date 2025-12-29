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
    if pipx_override in {"0", "false", "no", "pip", "unknown", "no-pip"}:
        return False

    exe = sys.executable.lower()
    return "pipx" in exe or "/pipx/venvs/" in exe or "\\pipx\\venvs\\" in exe


def _is_unknown_install() -> bool:
    """Check if we should mock an unknown installation method (e.g., uvx)."""
    return os.environ.get("SQLIT_MOCK_PIPX", "").strip().lower() == "unknown"


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
    if os.environ.get("SQLIT_MOCK_PIPX", "").strip().lower() == "no-pip":
        return False
    return importlib.util.find_spec("pip") is not None


def _user_site_enabled() -> bool:
    # site.ENABLE_USER_SITE already accounts for PYTHONNOUSERSITE and -s/-S in most cases.
    try:
        return bool(site.ENABLE_USER_SITE)
    except Exception:
        return False


def _is_arch_linux() -> bool:
    """Check if running on Arch Linux or derivative."""
    try:
        with open("/etc/os-release") as f:
            content = f.read().lower()
            return "arch" in content or "manjaro" in content or "endeavouros" in content
    except (FileNotFoundError, PermissionError):
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


def _get_arch_package_name(package_name: str) -> str | None:
    """Map PyPI package name to Arch Linux package name."""
    mapping = {
        "psycopg2-binary": "python-psycopg2",
        "psycopg2": "python-psycopg2",
        "mssql-python": "python-mssql",
        "mysql-connector-python": "python-mysql-connector",
        "mariadb": "python-mariadb-connector",
        "oracledb": "python-oracledb",
        "duckdb": "python-duckdb",
        "clickhouse-connect": "python-clickhouse-connect",
        "snowflake-connector-python": "python-snowflake-connector-python",
        "requests": "python-requests",
        "paramiko": "python-paramiko",
        "sshtunnel": "python-sshtunnel",
    }
    return mapping.get(package_name)


@dataclass(frozen=True)
class InstallOption:
    """A single install option with label and command."""

    label: str
    command: str


def get_install_options(package_name: str) -> list[InstallOption]:
    """Get list of install options for a package."""
    options = [
        InstallOption("pip", f"pip install {package_name}"),
        InstallOption("pipx", f"pipx inject sqlit-tui {package_name}"),
        InstallOption("uv", f"uv pip install {package_name}"),
        InstallOption("uvx", f"uvx --with {package_name} sqlit-tui"),
        InstallOption("poetry", f"poetry add {package_name}"),
        InstallOption("pdm", f"pdm add {package_name}"),
        InstallOption("conda", f"conda install {package_name}"),
    ]

    # Add Arch Linux options if on Arch
    if _is_arch_linux():
        arch_pkg = _get_arch_package_name(package_name)
        if arch_pkg:
            options.append(InstallOption("pacman", f"pacman -S {arch_pkg}"))
            options.append(InstallOption("yay", f"yay -S {arch_pkg}"))

    return options


def _format_manual_instructions(package_name: str, reason: str) -> str:
    """Format manual installation instructions with rich markup."""
    lines = [
        f"{reason}\n",
        "[bold]Install the driver using your preferred package manager:[/]\n",
    ]
    for opt in get_install_options(package_name):
        lines.append(f"  [cyan]{opt.label}[/]     {opt.command}")

    return "\n".join(lines)


def detect_strategy(*, extra_name: str, package_name: str) -> InstallStrategy:
    """Detect the best installation strategy for optional driver dependencies."""
    # When mocking driver errors, also force the no-pip path to show full instructions
    if os.environ.get("SQLIT_MOCK_DRIVER_ERROR"):
        return InstallStrategy(
            kind="no-pip",
            can_auto_install=False,
            manual_instructions=_format_manual_instructions(
                package_name,
                "pip is not available for this Python interpreter.",
            ),
            reason_unavailable="pip is not available.",
        )

    if _is_unknown_install():
        return InstallStrategy(
            kind="unknown",
            can_auto_install=False,
            manual_instructions=_format_manual_instructions(
                package_name,
                "Unable to detect how sqlit was installed.",
            ),
            reason_unavailable="Unable to detect installation method.",
        )

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
            manual_instructions=_format_manual_instructions(
                package_name,
                "This Python environment is externally managed (PEP 668).",
            ),
            reason_unavailable="Externally managed Python environment (PEP 668).",
        )

    if not _pip_available():
        return InstallStrategy(
            kind="no-pip",
            can_auto_install=False,
            manual_instructions=_format_manual_instructions(
                package_name,
                "pip is not available for this Python interpreter.",
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
        manual_instructions=_format_manual_instructions(
            package_name,
            "This Python environment is not writable and user-site installs are disabled.",
        ),
        reason_unavailable="Python environment not writable and user-site disabled.",
    )
