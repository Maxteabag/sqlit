from __future__ import annotations

import asyncio
import importlib
import os
import tempfile
import time
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _maybe_screenshot(app, name: str) -> None:
    outdir = os.environ.get("SQLIT_TEST_SCREENSHOTS_DIR")
    if not outdir:
        return
    Path(outdir).mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name)
    app.save_screenshot(path=outdir, filename=f"{safe}.svg")


def _assert_missing(module_name: str) -> None:
    try:
        importlib.import_module(module_name)
    except Exception:
        return
    raise AssertionError(f"Expected {module_name} to be missing, but it imported successfully")


def _assert_present(module_name: str) -> None:
    try:
        importlib.import_module(module_name)
    except Exception as e:
        raise AssertionError(f"Expected {module_name} to be importable, but got: {e}") from e


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
    os.environ["SQLIT_INSTALL_PROJECT_ROOT"] = str(_repo_root())

    if force_fail:
        os.environ["SQLIT_INSTALL_FORCE_FAIL"] = "1"
    else:
        os.environ.pop("SQLIT_INSTALL_FORCE_FAIL", None)

    from sqlit.app import SSMSTUI
    from sqlit.config import ConnectionConfig
    from sqlit.ui.screens.connection import ConnectionScreen

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

    app = SSMSTUI()
    async with app.run_test(size=(120, 40)) as pilot:
        app.push_screen(ConnectionScreen(config))
        await pilot.pause(0.2)
        _maybe_screenshot(app, f"{db_type}-01-connection")

        # Attempt to save should prompt to install missing driver
        app.screen.action_save()
        await _wait_for(
            pilot,
            lambda: app.screen.__class__.__name__ == "ConfirmScreen",
            timeout_s=5,
            label="ConfirmScreen",
        )
        # Give Textual a render tick so screenshots capture the modal contents
        await pilot.pause(0.2)
        _maybe_screenshot(app, f"{db_type}-02-confirm")
        await pilot.press("enter")

        if not force_fail:
            await _wait_for(
                pilot,
                lambda: app.screen.__class__.__name__ == "LoadingScreen",
                timeout_s=5,
                label="LoadingScreen",
            )
            await pilot.pause(0.2)
            _maybe_screenshot(app, f"{db_type}-03-loading")

        await _wait_for(
            pilot,
            lambda: app.screen.__class__.__name__ in ("MessageScreen", "ErrorScreen"),
            timeout_s=180,
            label="MessageScreen or ErrorScreen",
        )
        await pilot.pause(0.2)
        _maybe_screenshot(app, f"{db_type}-04-result")

        if force_fail:
            assert app.screen.__class__.__name__ == "ErrorScreen"
            err_text = getattr(app.screen, "message", "")
            if expected_manual not in err_text:
                raise AssertionError(f"Expected manual install hint in ErrorScreen, got:\n{err_text}")
        else:
            assert app.screen.__class__.__name__ == "MessageScreen"
            # No need to dismiss; success is established by reaching this screen.

    os.environ.pop("SQLIT_INSTALL_FORCE_FAIL", None)


async def main() -> None:
    # Success path: install missing psycopg2
    _assert_missing("psycopg2")
    await _run_flow(force_fail=False, db_type="postgresql")
    _assert_present("psycopg2")

    # Failure path: forced install failure yields manual instructions
    _assert_missing("mysql.connector")
    await _run_flow(force_fail=True, db_type="mysql")


if __name__ == "__main__":
    asyncio.run(main())
