from __future__ import annotations

import os
import subprocess
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


async def _wait_for(pilot, predicate, timeout_s: float, label: str) -> None:
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        if predicate():
            return
        await pilot.pause(0.1)
    app = getattr(pilot, "app", None)
    screen_name = getattr(getattr(app, "screen", None), "__class__", type("x", (), {})).__name__ if app else "unknown"
    raise AssertionError(f"Timed out waiting for: {label} (current screen: {screen_name})")


async def main() -> None:
    os.environ.setdefault("SQLIT_CONFIG_DIR", tempfile.mkdtemp(prefix="sqlit-test-config-"))
    outdir = os.environ.get("SQLIT_TEST_SCREENSHOTS_DIR")
    if outdir:
        _clean_screenshots_dir(Path(outdir))

    import sqlit.terminal as terminal_module
    import sqlit.ui.screens.connection as connection_screen_module
    from sqlit.app import SSMSTUI
    from sqlit.config import ConnectionConfig
    from sqlit.ui.screens.connection import ConnectionScreen

    class _DummyAdapter:
        def ensure_driver_available(self) -> None:
            return

    config = ConnectionConfig(
        name="mssql-driver-ui-flow",
        db_type="mssql",
        server="mssql",
        port="1433",
        database="master",
        username="sa",
        password="TestPassword123!",
    )

    app = SSMSTUI()
    async with app.run_test(size=(120, 40)) as pilot:
        # Avoid requiring pyodbc in this UI-only test.
        connection_screen_module.get_adapter = lambda _db_type: _DummyAdapter()  # type: ignore[assignment]

        app.push_screen(ConnectionScreen(config))
        await pilot.pause(0.2)
        _maybe_screenshot(app, "mssql-01-connection")

        screen = app.screen
        tabs = screen.query_one("#connection-tabs")
        tabs.active = "tab-advanced"
        await pilot.pause(0.2)
        _maybe_screenshot(app, "mssql-02-advanced")

        # Open driver setup (no drivers installed).
        screen._open_odbc_driver_setup(installed_drivers=[])
        await _wait_for(pilot, lambda: app.screen.__class__.__name__ == "DriverSetupScreen", 5, "DriverSetupScreen")
        await pilot.pause(0.2)
        _maybe_screenshot(app, "mssql-03-driver-setup-empty")

        # Trigger "Install" to show post-action message (run_in_terminal will likely fail in headless env).
        await pilot.press("i")
        await _wait_for(pilot, lambda: app.screen.__class__.__name__ == "MessageScreen", 5, "MessageScreen")
        await pilot.pause(0.2)
        _maybe_screenshot(app, "mssql-04-install-message")
        await pilot.press("enter")

        # After acknowledging, we return to the original setup screen (manual instructions remain there).
        await _wait_for(pilot, lambda: app.screen.__class__.__name__ == "DriverSetupScreen", 5, "DriverSetupScreen")
        await pilot.pause(0.2)
        _maybe_screenshot(app, "mssql-05-back-to-setup")

        await pilot.press("escape")
        await _wait_for(pilot, lambda: app.screen.__class__.__name__ == "ConnectionScreen", 5, "ConnectionScreen")
        await pilot.pause(0.2)
        _maybe_screenshot(app, "mssql-06-back-to-connection")

        # Simulate terminal found (successful run_in_terminal) and capture the success-path UI.
        os.environ["SQLIT_TEST_SCREENSHOTS_DIR"] = str(
            Path(os.environ["SQLIT_TEST_SCREENSHOTS_DIR"]) / "terminal-found"
        )

        terminal_module.run_in_terminal = (  # type: ignore[assignment]
            lambda _commands, wait_message="Press Enter to close...": terminal_module.TerminalResult(
                success=True, terminal=terminal_module.TerminalType.XTERM, error=None
            )
        )

        screen = app.screen
        tabs = screen.query_one("#connection-tabs")
        tabs.active = "tab-advanced"
        await pilot.pause(0.2)
        _maybe_screenshot(app, "mssql-01-advanced")

        screen._open_odbc_driver_setup(installed_drivers=[])
        await _wait_for(pilot, lambda: app.screen.__class__.__name__ == "DriverSetupScreen", 5, "DriverSetupScreen")
        await pilot.pause(0.2)
        _maybe_screenshot(app, "mssql-02-driver-setup-empty")

        await pilot.press("i")
        await _wait_for(pilot, lambda: app.screen.__class__.__name__ == "MessageScreen", 5, "MessageScreen")
        await pilot.pause(0.2)
        _maybe_screenshot(app, "mssql-03-install-message-terminal-found")
        await pilot.press("enter")

        await _wait_for(pilot, lambda: app.screen.__class__.__name__ == "ConnectionScreen", 5, "ConnectionScreen")
        await pilot.pause(0.2)
        _maybe_screenshot(app, "mssql-04-back-to-connection")

        # Open driver setup (drivers present) and select one.
        screen = app.screen
        tabs = screen.query_one("#connection-tabs")
        tabs.active = "tab-advanced"
        await pilot.pause(0.2)

        screen._open_odbc_driver_setup(installed_drivers=["ODBC Driver 18 for SQL Server"])
        await _wait_for(pilot, lambda: app.screen.__class__.__name__ == "DriverSetupScreen", 5, "DriverSetupScreen")
        await pilot.pause(0.2)
        _maybe_screenshot(app, "mssql-07-driver-setup-installed")

        await pilot.press("enter")
        await _wait_for(pilot, lambda: app.screen.__class__.__name__ == "ConnectionScreen", 5, "ConnectionScreen")

        # Verify the driver field reflects the selection.
        screen = app.screen
        tabs = screen.query_one("#connection-tabs")
        tabs.active = "tab-advanced"
        await pilot.pause(0.2)
        _maybe_screenshot(app, "mssql-08-driver-selected")

    # Convert SVGs to PNGs inside the container (avoids host permission issues).
    outdir = os.environ.get("SQLIT_TEST_SCREENSHOTS_DIR")
    if outdir:
        subprocess.run(
            [
                "bash",
                "-lc",
                f"command -v rsvg-convert >/dev/null 2>&1 && "
                f"find {outdir!s} -name '*.svg' -print0 | "
                'xargs -0 -I{} bash -lc \'rsvg-convert "$1" -o "${1%.svg}.png"\' _ {}',
            ],
            check=False,
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
