from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path


def _clean_screenshots_dir(outdir: Path) -> None:
    resolved = outdir.resolve()
    if resolved == Path("/"):
        raise AssertionError("Refusing to clean screenshots in '/'")
    if not outdir.exists():
        return
    for path in outdir.rglob("*"):
        if path.is_file() and path.suffix.lower() in (".svg", ".png"):
            path.unlink(missing_ok=True)


def _maybe_screenshot(app, name: str) -> None:
    outdir = os.environ.get("SQLIT_TEST_SCREENSHOTS_DIR")
    if not outdir:
        return
    Path(outdir).mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name)
    app.save_screenshot(path=outdir, filename=f"{safe}.svg")


class _FakeAsyncStream:
    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)

    def __aiter__(self):
        return self

    async def __anext__(self) -> bytes:
        if not self._lines:
            raise StopAsyncIteration
        return self._lines.pop(0).encode("utf-8")


class _FakeAsyncProcess:
    def __init__(self, return_code: int, lines: list[str]) -> None:
        self.returncode = return_code
        self.stdout = _FakeAsyncStream(lines)

    async def wait(self) -> int:
        return self.returncode

    def terminate(self) -> None:
        return None


class _FakeAsyncRunner:
    def __init__(self, return_code: int) -> None:
        self._return_code = return_code

    async def spawn(self, command: str) -> _FakeAsyncProcess:
        lines = [f"Running: {command}", "Done"]
        return _FakeAsyncProcess(self._return_code, lines)


async def _wait_for(pilot, predicate, timeout_s: float, label: str) -> None:
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        if predicate():
            return
        await pilot.pause(0.1)
    app = getattr(pilot, "app", None)
    screen_name = getattr(getattr(app, "screen", None), "__class__", type("x", (), {})).__name__ if app else "unknown"
    raise AssertionError(f"Timed out waiting for: {label} (current screen: {screen_name})")


async def _run_flow(*, force_fail: bool, db_type: str) -> None:
    os.environ.setdefault("SQLIT_CONFIG_DIR", tempfile.mkdtemp(prefix="sqlit-test-config-"))

    from sqlit.domains.connections.ui.screens.connection import ConnectionScreen
    from sqlit.domains.shell.app.main import SSMSTUI
    from sqlit.shared.app.runtime import RuntimeConfig
    from sqlit.shared.app.services import build_app_services
    from tests.helpers import ConnectionConfig

    if db_type == "postgresql":
        config = ConnectionConfig(
            name="pg-install-flow",
            db_type="postgresql",
            server="localhost",
            port="5432",
            database="postgres",
            username="test",
            password="test",
        )
        expected_manual = 'pip install "sqlit-tui[postgres]"'
    elif db_type == "mysql":
        config = ConnectionConfig(
            name="mysql-install-flow",
            db_type="mysql",
            server="localhost",
            port="3306",
            database="test_sqlit",
            username="test",
            password="test",
        )
        expected_manual = 'pip install "sqlit-tui[mysql]"'
    else:
        raise AssertionError(f"Unsupported db_type for test: {db_type}")

    runtime = RuntimeConfig()
    runtime.mock.missing_drivers = {db_type}
    services = build_app_services(runtime, async_process_runner=_FakeAsyncRunner(1 if force_fail else 0))
    app = SSMSTUI(services=services)
    app.restart = lambda: None
    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen(ConnectionScreen(config))
        await pilot.pause(0.2)
        _maybe_screenshot(app, f"{db_type}-01-connection")

        # Attempt to save should show the package setup dialog
        app.screen.action_save()
        await _wait_for(
            pilot,
            lambda: app.screen.__class__.__name__ == "PackageSetupScreen",
            timeout_s=5,
            label="PackageSetupScreen",
        )
        # Give Textual a render tick so screenshots capture the modal contents
        await pilot.pause(0.2)
        _maybe_screenshot(app, f"{db_type}-02-setup")
        await pilot.press("enter")

        await _wait_for(
            pilot,
            lambda: app.screen.__class__.__name__ == "InstallProgressScreen",
            timeout_s=5,
            label="InstallProgressScreen",
        )
        await _wait_for(
            pilot,
            lambda: app.screen.__class__.__name__ == "InstallProgressScreen"
            and getattr(app.screen, "_completed", False),
            timeout_s=10,
            label="InstallProgressScreen (completed)",
        )
        await pilot.press("enter")

        # Return to the ConnectionScreen after install attempt.
        await _wait_for(
            pilot,
            lambda: app.screen.__class__.__name__ == "ConnectionScreen",
            timeout_s=5,
            label="ConnectionScreen (after install)",
        )

        # If failure, ensure manual install hint remains visible.
        if force_fail:
            await pilot.pause(0.2)
            _maybe_screenshot(app, f"{db_type}-04-result")

            from textual.widgets import Static

            text = str(app.screen.query_one("#test-status", Static).content)
            if expected_manual not in text:
                raise AssertionError(f"Expected manual install hint in connection screen, got:\n{text}")
        else:
            assert app.screen.__class__.__name__ == "ConnectionScreen"
            await pilot.pause(0.2)
            _maybe_screenshot(app, f"{db_type}-04-result")


async def main() -> None:
    outdir = os.environ.get("SQLIT_TEST_SCREENSHOTS_DIR")
    if outdir:
        _clean_screenshots_dir(Path(outdir))

    # Success path: simulated driver install
    await _run_flow(force_fail=False, db_type="postgresql")

    # Failure path: simulated install failure yields manual instructions
    await _run_flow(force_fail=True, db_type="mysql")


if __name__ == "__main__":
    asyncio.run(main())
