from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.conftest import run_cli


def _run_cli_with_stdin(*args: str, stdin: str, env_config_dir: Path) -> subprocess.CompletedProcess:
    """Invoke the sqlit CLI with a piped stdin payload."""
    cmd = [sys.executable, "-m", "sqlit.cli", *args]
    return subprocess.run(
        cmd,
        input=stdin,
        capture_output=True,
        text=True,
        cwd=str(env_config_dir),
        env={
            "SQLIT_CONFIG_DIR": str(env_config_dir),
            "PATH": __import__("os").environ.get("PATH", ""),
            "PYTHONPATH": __import__("os").environ.get("PYTHONPATH", ""),
        },
    )


def test_cli_connections_list_empty(tmp_path: Path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"allow_plaintext_credentials": true}', encoding="utf-8")

    monkeypatch.setenv("SQLIT_CONFIG_DIR", str(tmp_path))

    result = run_cli("connections", "list", check=False)

    assert result.returncode == 0
    assert "No saved connections." in result.stdout


def test_url_stdin_creates_connection(tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"allow_plaintext_credentials": true}', encoding="utf-8")

    result = _run_cli_with_stdin(
        "connections", "add", "--url-stdin", "--name", "StdinURL",
        stdin="sqlite:///tmp/sqlit-stdin-test.db\n",
        env_config_dir=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert "StdinURL" in result.stdout


def test_url_stdin_rejects_when_url_also_provided(tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"allow_plaintext_credentials": true}', encoding="utf-8")

    result = _run_cli_with_stdin(
        "connections", "add",
        "--url", "sqlite:///tmp/a.db",
        "--url-stdin",
        "--name", "X",
        stdin="sqlite:///tmp/b.db\n",
        env_config_dir=tmp_path,
    )

    assert result.returncode != 0
    assert "mutually exclusive" in (result.stderr + result.stdout)


def test_password_stdin_mutex_with_password(tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"allow_plaintext_credentials": true}', encoding="utf-8")

    result = _run_cli_with_stdin(
        "connect", "postgresql",
        "--name", "X",
        "--server", "localhost",
        "--port", "5432",
        "--database", "d",
        "--username", "u",
        "--password", "cleartext",
        "--password-stdin",
        stdin="frompipe\n",
        env_config_dir=tmp_path,
    )

    assert result.returncode != 0
    assert "mutually exclusive" in (result.stderr + result.stdout)


def test_multiple_stdin_flags_rejected(tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"allow_plaintext_credentials": true}', encoding="utf-8")

    result = _run_cli_with_stdin(
        "connections", "edit", "Nonexistent",
        "--password-stdin",
        "--ssh-password-stdin",
        stdin="x\n",
        env_config_dir=tmp_path,
    )

    assert result.returncode != 0
    output = result.stderr + result.stdout
    assert "only one" in output and "stdin" in output


def test_password_stdin_eof_errors_cleanly(tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"allow_plaintext_credentials": true}', encoding="utf-8")

    result = _run_cli_with_stdin(
        "connect", "postgresql",
        "--name", "X",
        "--server", "localhost",
        "--port", "5432",
        "--database", "d",
        "--username", "u",
        "--password-stdin",
        stdin="",
        env_config_dir=tmp_path,
    )

    assert result.returncode != 0
    assert "EOF" in (result.stderr + result.stdout)


def test_cli_version_option(tmp_path: Path):
    result = _run_cli_with_stdin(
        "--version",
        stdin="",
        env_config_dir=tmp_path,
    )
    assert result.returncode == 0
    assert "sqlit" in result.stdout


def test_cli_version_short_option(tmp_path: Path):
    result = _run_cli_with_stdin(
        "-v",
        stdin="",
        env_config_dir=tmp_path,
    )
    assert result.returncode == 0
    assert "sqlit" in result.stdout
