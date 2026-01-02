"""Lightweight startup profiling logger."""

from __future__ import annotations

import importlib.machinery
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_log_path: Path | None = None
_start_mark: float | None = None
_init_mark: float | None = None
_initialized: bool = False
_import_log_path: Path | None = None
_import_min_ms: float = 0.0
_import_initialized: bool = False
_import_enabled: bool = False


def configure(
    *,
    log_path: Path | None,
    start_mark: float | None = None,
    init_mark: float | None = None,
    clear: bool = False,
) -> None:
    """Configure the startup profiler output."""
    global _log_path, _start_mark, _init_mark, _initialized
    _log_path = log_path
    if start_mark is not None:
        _start_mark = start_mark
    if init_mark is not None:
        _init_mark = init_mark
    if not log_path:
        return
    if clear:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "w", encoding="utf-8"):
                pass
            _initialized = True
        except Exception:
            _initialized = False


def write_line(line: str) -> None:
    """Write a startup log line to the configured file, if any."""
    global _initialized
    if _log_path is None:
        return
    try:
        _log_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if _initialized else "w"
        _initialized = True
        with open(_log_path, mode, encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass


def _write_import_line(line: str) -> None:
    """Write an import timing line to the configured import log, if any."""
    global _import_initialized
    if _import_log_path is None:
        return
    try:
        _import_log_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if _import_initialized else "w"
        _import_initialized = True
        with open(_import_log_path, mode, encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass


def log_step(name: str, *, timestamp: float | None = None) -> None:
    """Log a point-in-time startup step."""
    if _log_path is None:
        return
    now = timestamp if timestamp is not None else time.perf_counter()
    parts = [f"step={name}"]
    if _start_mark is not None:
        parts.append(f"start_ms={(now - _start_mark) * 1000:.2f}")
    init_base = _init_mark if _init_mark is not None else _start_mark
    if init_base is not None:
        parts.append(f"init_ms={(now - init_base) * 1000:.2f}")
    write_line(f"[sqlit] startup {' '.join(parts)}")


@contextmanager
def span(name: str) -> Iterator[None]:
    """Measure a span and log its duration."""
    if _log_path is None:
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        write_line(f"[sqlit] startup span={name} dur_ms={duration_ms:.2f}")


class _ImportTimerLoader:
    def __init__(self, loader: object, fullname: str) -> None:
        self._loader = loader
        self._fullname = fullname

    def create_module(self, spec: object) -> object | None:
        create = getattr(self._loader, "create_module", None)
        if callable(create):
            return create(spec)
        return None

    def exec_module(self, module: object) -> None:
        start = time.perf_counter()
        try:
            exec_module = getattr(self._loader, "exec_module", None)
            if callable(exec_module):
                exec_module(module)
                return
            load_module = getattr(self._loader, "load_module", None)
            if callable(load_module):
                load_module(self._fullname)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            if duration_ms >= _import_min_ms:
                _write_import_line(
                    f"[sqlit] import name={self._fullname} dur_ms={duration_ms:.2f}"
                )


class _ImportTimerFinder:
    def find_spec(self, fullname: str, path: object | None, target: object | None = None) -> object | None:
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if spec is None or getattr(spec, "loader", None) is None:
            return spec
        if isinstance(spec.loader, _ImportTimerLoader):
            return spec
        spec.loader = _ImportTimerLoader(spec.loader, fullname)
        return spec


def enable_import_timing(*, log_path: Path | None, min_ms: float = 0.0) -> None:
    """Enable per-module import timing output to a file."""
    global _import_log_path, _import_min_ms, _import_initialized, _import_enabled
    if not log_path or _import_enabled:
        return
    _import_log_path = log_path
    _import_min_ms = max(0.0, float(min_ms))
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w", encoding="utf-8"):
            pass
        _import_initialized = True
    except Exception:
        _import_initialized = False
    sys.meta_path.insert(0, _ImportTimerFinder())
    _import_enabled = True
