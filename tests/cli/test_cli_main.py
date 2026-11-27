from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_cli_edit_selects_postgres_entra_auth(tmp_path: Path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"allow_plaintext_credentials": true}', encoding="utf-8")
    monkeypatch.setenv("SQLIT_CONFIG_DIR", str(tmp_path))
    created = run_cli(
        "connections",
        "add",
        "postgresql",
        "--name",
        "Azure",
        "--server",
        "localhost",
        "--username",
        "developer",
        "--password",
        "old-password",
        check=False,
    )
    assert created.returncode == 0, created.stderr

    edited = run_cli(
        "connections",
        "edit",
        "Azure",
        "--postgres-auth-method",
        "azure_entra_cli",
        "--password",
        "must-not-be-kept",
        check=False,
    )

    assert edited.returncode == 0, edited.stderr
    payload = json.loads((tmp_path / "connections.json").read_text())
    saved = payload["connections"][0]
    assert saved["options"]["postgres_auth_method"] == "azure_entra_cli"
    assert saved["endpoint"]["password"] is None
    assert saved["endpoint"]["password_command"].startswith("az account get-access-token")

    edited_again = run_cli(
        "connections",
        "edit",
        "Azure",
        "--password",
        "still-must-not-be-kept",
        check=False,
    )
    assert edited_again.returncode == 0, edited_again.stderr
    payload = json.loads((tmp_path / "connections.json").read_text())
    assert payload["connections"][0]["endpoint"]["password"] is None
    assert payload["connections"][0]["options"]["postgres_auth_method"] == "azure_entra_cli"


def test_cli_preserves_legacy_azure_password_command(tmp_path: Path, monkeypatch):
    from sqlit.domains.connections.providers.postgresql.auth import (
        AZURE_ENTRA_PASSWORD_COMMAND,
    )

    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"allow_plaintext_credentials": true}', encoding="utf-8")
    monkeypatch.setenv("SQLIT_CONFIG_DIR", str(tmp_path))

    result = run_cli(
        "connections",
        "add",
        "postgresql",
        "--name",
        "LegacyAzure",
        "--server",
        "localhost",
        "--username",
        "developer",
        "--password-command",
        AZURE_ENTRA_PASSWORD_COMMAND,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads((tmp_path / "connections.json").read_text())
    saved = payload["connections"][0]
    assert saved["options"]["postgres_auth_method"] == "azure_entra_cli"
    assert saved["endpoint"]["password_command"] == AZURE_ENTRA_PASSWORD_COMMAND


def test_url_stdin_creates_connection(tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"allow_plaintext_credentials": true}', encoding="utf-8")

    result = _run_cli_with_stdin(
        "connections",
        "add",
        "--url-stdin",
        "--name",
        "StdinURL",
        stdin="sqlite:///tmp/sqlit-stdin-test.db\n",
        env_config_dir=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert "StdinURL" in result.stdout


def test_url_stdin_rejects_when_url_also_provided(tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"allow_plaintext_credentials": true}', encoding="utf-8")

    result = _run_cli_with_stdin(
        "connections",
        "add",
        "--url",
        "sqlite:///tmp/a.db",
        "--url-stdin",
        "--name",
        "X",
        stdin="sqlite:///tmp/b.db\n",
        env_config_dir=tmp_path,
    )

    assert result.returncode != 0
    assert "mutually exclusive" in (result.stderr + result.stdout)


def test_password_stdin_mutex_with_password(tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"allow_plaintext_credentials": true}', encoding="utf-8")

    result = _run_cli_with_stdin(
        "connect",
        "postgresql",
        "--name",
        "X",
        "--server",
        "localhost",
        "--port",
        "5432",
        "--database",
        "d",
        "--username",
        "u",
        "--password",
        "cleartext",
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
        "connections",
        "edit",
        "Nonexistent",
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
        "connect",
        "postgresql",
        "--name",
        "X",
        "--server",
        "localhost",
        "--port",
        "5432",
        "--database",
        "d",
        "--username",
        "u",
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


@pytest.fixture
def sqlite_cli(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SQLIT_CONFIG_DIR", str(tmp_path))
    db = tmp_path / "demo.db"
    created = run_cli("connections", "add", "sqlite", "--name", "d", "--file-path", str(db), check=False)
    assert created.returncode == 0, created.stdout + created.stderr

    def query(*args: str) -> subprocess.CompletedProcess:
        return run_cli("query", "-c", "d", "--format", "json", *args, check=False)

    return query


def test_sqlite_script_shows_only_last_result(tmp_path: Path, sqlite_cli):
    script = tmp_path / "script.sql"
    script.write_text(
        "create table z(a int);\n"
        "-- seed; comment\n"
        "insert into z values (1) returning a;\n"
        "/* last; result */ select a from z /* end of query */\n"
        "-- trailing comment;",
        encoding="utf-8",
    )

    result = sqlite_cli("-f", str(script))
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == [{"a": 1}]


@pytest.mark.parametrize(
    ("explicit_transaction", "failing_statement", "error", "expected"),
    [
        (False, "insert into z values (1)", "UNIQUE constraint failed: z.a", [{"a": 1}]),
        (True, "insert into z values (1)", "UNIQUE constraint failed: z.a", []),
        (False, "select abs(column1) from (values (1), (-9223372036854775808))", "integer overflow", [{"a": 1}]),
    ],
)
def test_sqlite_script_stops_at_first_error(
    tmp_path: Path, sqlite_cli, explicit_transaction, failing_statement, error, expected
):
    setup = sqlite_cli("-q", "create table z(a int unique)")
    assert setup.returncode == 0, setup.stdout + setup.stderr
    script = tmp_path / "script.sql"
    script.write_text(
        ("begin;\n" if explicit_transaction else "")
        + "insert into z values (1);\n"
        + f"{failing_statement};\n"
        + "insert into z values (2);\n"
        + ("commit;\n" if explicit_transaction else "")
        + "select * from z;",
        encoding="utf-8",
    )

    result = sqlite_cli("-f", str(script))
    assert result.returncode == 1
    assert error in result.stdout

    readback = sqlite_cli("-q", "select * from z order by a")
    assert readback.returncode == 0, readback.stdout + readback.stderr
    assert json.loads(readback.stdout) == expected


@pytest.mark.parametrize("in_script", [False, True])
def test_sqlite_trigger_body_with_internal_semicolons(tmp_path: Path, sqlite_cli, in_script):
    setup = sqlite_cli("-q", "create table z(a int)")
    assert setup.returncode == 0, setup.stdout + setup.stderr
    trigger = (
        "create trigger log_insert after insert on z when new.a = 1 begin\n"
        "  insert into z values (2);\n"
        "  insert into z values (3);\n"
        "end"
    )
    script = tmp_path / "trigger.sql"
    query = "insert into z values (1); select * from z order by a"
    script.write_text(f"\ufeff{trigger};\n{query}" if in_script else trigger, encoding="utf-8")

    result = sqlite_cli("-f", str(script))
    assert result.returncode == 0, result.stdout + result.stderr
    if not in_script:
        inserted = sqlite_cli("-q", "insert into z values (1)")
        assert inserted.returncode == 0, inserted.stdout + inserted.stderr
        result = sqlite_cli("-q", "select * from z order by a")
        assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == [{"a": 1}, {"a": 2}, {"a": 3}]
