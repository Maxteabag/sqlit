"""System probe helpers for install strategy detection."""

from __future__ import annotations

import importlib.util
import os
import site
import sys
import sysconfig
from pathlib import Path
from typing import Callable, Mapping


def _safe_sysconfig_paths() -> dict[str, str]:
    try:
        paths = sysconfig.get_paths()
        return dict(paths) if isinstance(paths, dict) else {}
    except Exception:
        return {}


def _safe_stdlib_paths() -> list[str]:
    paths: list[str] = []
    for key in ("stdlib", "platstdlib"):
        try:
            value = sysconfig.get_path(key)
        except Exception:
            value = None
        if value:
            paths.append(value)
    return paths


def _read_os_release() -> str | None:
    try:
        with open("/etc/os-release", encoding="utf-8") as handle:
            return handle.read()
    except (FileNotFoundError, PermissionError):
        return None


class SystemProbe:
    """Snapshot of system state used for install strategy detection."""

    def __init__(
        self,
        *,
        env: Mapping[str, str] | None = None,
        executable: str | None = None,
        prefix: str | None = None,
        base_prefix: str | None = None,
        uv_env: bool | None = None,
        conda_prefix: str | None = None,
        user_site_enabled: bool | None = None,
        sysconfig_paths: Mapping[str, str] | None = None,
        stdlib_paths: list[str] | None = None,
        pip_available: bool | None = None,
        os_release_content: str | None = None,
        path_writable: Callable[[Path], bool] | None = None,
    ) -> None:
        self._env = env or os.environ
        self._executable = executable or sys.executable
        self._prefix = prefix or sys.prefix
        self._base_prefix = base_prefix or getattr(sys, "base_prefix", sys.prefix)
        self._uv_env = bool(uv_env) if uv_env is not None else bool(self._env.get("UV"))
        self._conda_prefix = conda_prefix if conda_prefix is not None else self._env.get("CONDA_PREFIX")
        self._user_site_enabled = (
            bool(user_site_enabled) if user_site_enabled is not None else bool(getattr(site, "ENABLE_USER_SITE", False))
        )
        self._sysconfig_paths = dict(sysconfig_paths) if sysconfig_paths is not None else _safe_sysconfig_paths()
        self._stdlib_paths = list(stdlib_paths) if stdlib_paths is not None else _safe_stdlib_paths()
        self._pip_available = (
            bool(pip_available) if pip_available is not None else importlib.util.find_spec("pip") is not None
        )
        self._os_release_content = os_release_content if os_release_content is not None else _read_os_release()
        self._path_writable = path_writable or (lambda path: os.access(path, os.W_OK))

    @property
    def executable(self) -> str:
        return self._executable

    def env_value(self, key: str) -> str:
        return str(self._env.get(key, ""))

    def in_venv(self) -> bool:
        if self.env_value("VIRTUAL_ENV"):
            return True
        return self._prefix != self._base_prefix

    def is_pipx(self) -> bool:
        exe = self._executable.lower()
        return "/pipx/venvs/" in exe or "\\pipx\\venvs\\" in exe

    def is_uvx(self) -> bool:
        exe = self._executable.lower()
        return "/uv/tools/" in exe or "\\uv\\tools\\" in exe

    def is_uv_run(self) -> bool:
        return self._uv_env

    def is_conda(self) -> bool:
        return bool(self._conda_prefix)

    def pep668_externally_managed(self) -> bool:
        if self.in_venv():
            return False
        for stdlib_path in self._stdlib_paths:
            marker = Path(stdlib_path) / "EXTERNALLY-MANAGED"
            if marker.exists():
                return True
        return False

    def pip_available(self) -> bool:
        return self._pip_available

    def user_site_enabled(self) -> bool:
        return self._user_site_enabled

    def is_arch_linux(self) -> bool:
        content = (self._os_release_content or "").lower()
        return "arch" in content or "manjaro" in content or "endeavouros" in content

    def install_paths_writable(self) -> bool:
        for key in ("purelib", "platlib"):
            value = self._sysconfig_paths.get(key)
            if not value:
                continue
            path = Path(value)
            probe = path if path.exists() else path.parent
            if probe.exists() and self._path_writable(probe):
                return True
        return False
