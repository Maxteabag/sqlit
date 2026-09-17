"""Tests for the pre-spawn helper in cli.py and the SSMSTUI kwarg plumbing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sqlit.cli import _prewarm_process_worker
from sqlit.shared.app.runtime import MockConfig, RuntimeConfig


def test_prewarm_skipped_when_worker_disabled() -> None:
    runtime = RuntimeConfig(process_worker=False)
    with patch("sqlit.domains.process_worker.app.process_worker_client.ProcessWorkerClient") as klass:
        result = _prewarm_process_worker(runtime)
    assert result is None
    klass.assert_not_called()


def test_prewarm_skipped_when_mock_enabled() -> None:
    runtime = RuntimeConfig(process_worker=True, mock=MockConfig(enabled=True))
    with patch("sqlit.domains.process_worker.app.process_worker_client.ProcessWorkerClient") as klass:
        result = _prewarm_process_worker(runtime)
    assert result is None
    klass.assert_not_called()


def test_prewarm_returns_client_when_enabled() -> None:
    runtime = RuntimeConfig(process_worker=True)
    sentinel = MagicMock(name="process-worker-client")
    with patch(
        "sqlit.domains.process_worker.app.process_worker_client.ProcessWorkerClient",
        return_value=sentinel,
    ):
        result = _prewarm_process_worker(runtime)
    assert result is sentinel


def test_prewarm_swallows_spawn_errors() -> None:
    """A failing pre-spawn must not break startup; lazy path handles fallback."""
    runtime = RuntimeConfig(process_worker=True)
    with patch(
        "sqlit.domains.process_worker.app.process_worker_client.ProcessWorkerClient",
        side_effect=ValueError("bad value(s) in fds_to_keep"),
    ):
        result = _prewarm_process_worker(runtime)
    assert result is None


def test_ssmstui_stashes_prewarmed_worker() -> None:
    """A client passed via the kwarg should land on self._process_worker_client.

    ProcessWorkerLifecycleMixin returns that attribute first, so this is
    what makes the pre-spawn actually short-circuit the lazy path.
    """
    from sqlit.domains.shell.app.main import SSMSTUI
    from tests.ui.mocks import MockConnectionStore, MockSettingsStore, build_test_services, create_test_connection

    services = build_test_services(
        connection_store=MockConnectionStore([create_test_connection("test-db", "sqlite")]),
        settings_store=MockSettingsStore({}),
    )
    sentinel = MagicMock(name="process-worker-client")
    app = SSMSTUI(services=services, process_worker_client=sentinel)
    assert app._process_worker_client is sentinel
