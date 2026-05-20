"""Tests for the macOS fork-fallback guard and the worker log redirect."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlit.domains.process_worker.app.process_worker import _open_worker_log
from sqlit.domains.process_worker.app.process_worker_client import ProcessWorkerClient


def _make_client_without_init() -> ProcessWorkerClient:
    """Build a bare ProcessWorkerClient instance without running __init__.

    __init__ spawns a real subprocess; we only want to exercise the
    in-process branching logic in _maybe_fallback_start.
    """
    return ProcessWorkerClient.__new__(ProcessWorkerClient)


def test_fork_fallback_disabled_on_darwin(monkeypatch: pytest.MonkeyPatch) -> None:
    """On macOS the fallback path must re-raise instead of forking."""
    monkeypatch.setattr("sys.platform", "darwin")
    client = _make_client_without_init()

    error = ValueError("bad value(s) in fds_to_keep")
    with pytest.raises(ValueError, match="fds_to_keep"):
        client._maybe_fallback_start(error)


def test_fork_fallback_skips_non_fds_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Errors unrelated to fds_to_keep should always re-raise verbatim."""
    monkeypatch.setattr("sys.platform", "linux")
    client = _make_client_without_init()

    error = ValueError("totally unrelated message")
    with pytest.raises(ValueError, match="totally unrelated"):
        client._maybe_fallback_start(error)


def test_worker_log_honors_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """SQLIT_WORKER_LOG should redirect the worker log to a custom path."""
    target = tmp_path / "subdir" / "worker.log"
    monkeypatch.setenv("SQLIT_WORKER_LOG", str(target))

    log_file = _open_worker_log()
    assert log_file is not None
    try:
        log_file.write("hello\n")
    finally:
        log_file.close()

    assert target.exists()
    assert "hello" in target.read_text()


def test_worker_log_returns_none_on_unwritable_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the log path can't be opened, the worker should still boot."""
    # A path whose parent can't be created (root-owned, non-existent).
    monkeypatch.setenv("SQLIT_WORKER_LOG", "/proc/definitely/not/writable/here.log")

    log_file = _open_worker_log()
    assert log_file is None
