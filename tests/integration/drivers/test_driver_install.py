#!/usr/bin/env python3
"""Integration test for ODBC driver installation."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import time


def log(message: str, level: str = "INFO") -> None:
    distro = os.environ.get("DISTRO_NAME", "unknown")
    print(f"[{distro}] [{level}] {message}", flush=True)


def run_command(command: str) -> tuple[int, str, str]:
    log(f"Running: {command}")
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.stdout:
        for line in result.stdout.strip().split("\n"):
            log(f"  stdout: {line}")
    if result.stderr:
        for line in result.stderr.strip().split("\n"):
            log(f"  stderr: {line}")
    return result.returncode, result.stdout, result.stderr


def check_no_driver_initially() -> bool:
    log("Step 1: Checking that no ODBC driver is installed initially...")

    from sqlit.drivers import get_installed_drivers

    drivers = get_installed_drivers()
    if drivers:
        log(f"Unexpected: Found drivers already installed: {drivers}", "WARN")
        return True

    log("Confirmed: No SQL Server ODBC drivers found initially")
    return True


def get_install_commands_for_os() -> list[str] | None:
    log("Step 2: Getting installation commands for this OS...")

    from sqlit.drivers import get_install_commands, get_os_info

    os_type, os_version = get_os_info()
    log(f"Detected OS: {os_type} {os_version}")

    install_cmd = get_install_commands()
    if not install_cmd:
        log(f"No installation commands available for {os_type}", "ERROR")
        return None

    log(f"Installation method: {install_cmd.description}")
    for warning in install_cmd.warnings:
        log(warning, "WARN")

    log(f"Commands to execute ({len(install_cmd.commands)}):")
    for i, cmd in enumerate(install_cmd.commands, 1):
        log(f"  {i}. {cmd}")

    return install_cmd.commands


def execute_install_commands(commands: list[str]) -> bool:
    log("Step 3: Executing installation commands...")

    for i, command in enumerate(commands, 1):
        # Strip sudo since we're running as root in the container
        if command.startswith("sudo "):
            command = command[5:]
        command = command.replace(" sudo ", " ")

        # Make AUR helpers non-interactive for testing
        # Also run as non-root user since yay doesn't like running as root
        if command.startswith("yay -S "):
            command = command.replace("yay -S ", "yay -S --noconfirm ")
            command = f"su - builder -c '{command}'"

        log(f"Executing command {i}/{len(commands)}")
        exit_code, _, _ = run_command(command)

        if exit_code != 0:
            if "|| true" in command or "2>/dev/null" in command:
                log(f"Command {i} failed but was optional, continuing...")
                continue
            log(f"Command {i} failed with exit code {exit_code}", "ERROR")
            return False

    log("All installation commands completed successfully")
    return True


def verify_driver_installed() -> str | None:
    log("Step 4: Verifying driver is now installed...")

    import sqlit.drivers

    importlib.reload(sqlit.drivers)

    from sqlit.drivers import get_best_driver, get_installed_drivers

    drivers = get_installed_drivers()
    if not drivers:
        log("No ODBC drivers found after installation", "ERROR")
        return None

    log(f"Found installed drivers: {drivers}")
    best = get_best_driver()
    log(f"Best available driver: {best}")
    return best


def verify_connection(driver: str) -> bool:
    log("Step 5: Testing connection to SQL Server...")

    host = os.environ.get("MSSQL_HOST", "localhost")
    port = os.environ.get("MSSQL_PORT", "1433")
    user = os.environ.get("MSSQL_USER", "sa")
    password = os.environ.get("MSSQL_PASSWORD")

    if not password:
        log("MSSQL_PASSWORD environment variable not set", "ERROR")
        return False

    log(f"Connecting to {host}:{port} as {user}...")

    try:
        import pyodbc

        conn_str = (
            f"DRIVER={{{driver}}};"
            f"SERVER={host},{port};"
            f"UID={user};"
            f"PWD={password};"
            f"TrustServerCertificate=yes;"
        )

        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                log(f"Connection attempt {attempt}/{max_retries}...")
                conn = pyodbc.connect(conn_str, timeout=10)
                cursor = conn.cursor()
                cursor.execute("SELECT @@VERSION")
                version = cursor.fetchone()[0]
                log("Connected successfully!")
                log(f"SQL Server version: {version[:80]}...")
                cursor.close()
                conn.close()
                return True
            except pyodbc.Error as e:
                log(f"Connection attempt {attempt} failed: {e}", "WARN")
                if attempt < max_retries:
                    time.sleep(5)

        log("All connection attempts failed", "ERROR")
        return False

    except Exception as e:
        log(f"Connection test failed with exception: {e}", "ERROR")
        return False


def main() -> int:
    log("=" * 60)
    log("ODBC Driver Installation Integration Test")
    log("=" * 60)

    distro = os.environ.get("DISTRO_NAME", "unknown")
    log(f"Testing on: {distro}")

    if not check_no_driver_initially():
        return 1

    commands = get_install_commands_for_os()
    if commands is None:
        return 1

    if not execute_install_commands(commands):
        return 1

    driver = verify_driver_installed()
    if driver is None:
        return 1

    if not verify_connection(driver):
        return 1

    log("=" * 60)
    log("ALL TESTS PASSED", "SUCCESS")
    log("=" * 60)
    return 0


def test_driver_install_integration() -> None:
    """Run the full driver installation integration test.

    This test is skipped unless MSSQL_PASSWORD is set, indicating
    we're running in the proper CI environment with Docker.
    """
    import pytest

    if not os.environ.get("MSSQL_PASSWORD"):
        pytest.skip("MSSQL_PASSWORD not set - skipping integration test")

    result = main()
    assert result == 0, "Driver installation integration test failed"


if __name__ == "__main__":
    sys.exit(main())
