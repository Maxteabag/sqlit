from __future__ import annotations

import subprocess
import threading
from unittest.mock import MagicMock, patch

from sqlit.domains.connections.app.installer import Installer
from sqlit.domains.connections.providers.exceptions import MissingDriverError


class _FakeProcess:
    def __init__(self, started_event: threading.Event):
        self.started_event = started_event
        self.terminated = False
        self.killed = False
        self.returncode: int | None = None
        self.started_event.set()

    def communicate(self, timeout: float | None = None):  # noqa: ANN001
        if self.terminated or self.killed:
            self.returncode = -15 if self.terminated else -9
            return "", ""
        raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None) -> int:  # noqa: ARG002
        self.returncode = -15 if self.terminated else -9 if self.killed else 0
        return self.returncode


class _FakeRunner:
    def __init__(self, started_event: threading.Event, holder: dict[str, _FakeProcess]) -> None:
        self._started_event = started_event
        self._holder = holder

    def spawn(self, command, *, cwd=None):  # noqa: ANN001,ARG002
        proc = _FakeProcess(self._started_event)
        self._holder["proc"] = proc
        return proc


def test_installer_cancel_terminates_process():
    error = MissingDriverError("PostgreSQL", "postgres", "psycopg2-binary")
    cancel_event = threading.Event()

    started = threading.Event()
    proc_holder: dict[str, _FakeProcess] = {}
    runner = _FakeRunner(started, proc_holder)
    installer = Installer(app=object(), process_runner=runner)

    fake_strategy = MagicMock()
    fake_strategy.can_auto_install = True
    fake_strategy.auto_install_command = ["pip", "install", "psycopg2-binary"]

    with patch("sqlit.domains.connections.app.installer.detect_strategy", return_value=fake_strategy):
        result_holder: dict[str, tuple[bool, str, MissingDriverError]] = {}

        def run():
            result_holder["result"] = installer._do_install(error, cancel_event)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

        assert started.wait(timeout=1)
        cancel_event.set()
        thread.join(timeout=5)
        assert not thread.is_alive()

        success, output, _ = result_holder["result"]
        assert success is False
        assert "cancelled" in output.lower()
        assert proc_holder["proc"].terminated is True
