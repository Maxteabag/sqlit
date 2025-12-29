from __future__ import annotations

import subprocess
import threading
from unittest.mock import MagicMock, patch

from sqlit.db.exceptions import MissingDriverError
from sqlit.services.installer import Installer


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


def test_installer_cancel_terminates_process():
    installer = Installer(app=object())
    error = MissingDriverError("PostgreSQL", "postgres", "psycopg2-binary")
    cancel_event = threading.Event()

    started = threading.Event()
    proc_holder: dict[str, _FakeProcess] = {}

    def fake_popen(*args, **kwargs):  # noqa: ANN001,ARG001
        proc = _FakeProcess(started)
        proc_holder["proc"] = proc
        return proc

    fake_strategy = MagicMock()
    fake_strategy.can_auto_install = True
    fake_strategy.auto_install_command = ["pip", "install", "psycopg2-binary"]

    with (
        patch("sqlit.services.installer.subprocess.Popen", new=fake_popen),
        patch("sqlit.services.installer.detect_strategy", return_value=fake_strategy),
    ):
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
