"""Tests for shell tab-completion support (issue #247)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sqlit.domains.connections.cli import completion


def _write_connections(config_dir: Path, payload: object) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "connections.json").write_text(json.dumps(payload), encoding="utf-8")


# --------------------------------------------------------------------------
# Unit tests for the connection-name completer
# --------------------------------------------------------------------------


def test_complete_connection_names_v2_format(tmp_path: Path, monkeypatch):
    _write_connections(
        tmp_path,
        {"version": 2, "connections": [{"name": "prod-pg"}, {"name": "prod-mysql"}, {"name": "staging"}]},
    )
    # The completer reads CONFIG_DIR lazily from the store module.
    monkeypatch.setattr("sqlit.shared.core.store.CONFIG_DIR", tmp_path)

    assert completion.complete_connection_names("prod") == ["prod-pg", "prod-mysql"]
    assert set(completion.complete_connection_names("")) == {"prod-pg", "prod-mysql", "staging"}
    assert completion.complete_connection_names("zzz") == []


def test_complete_connection_names_legacy_list_format(tmp_path: Path, monkeypatch):
    _write_connections(tmp_path, [{"name": "legacy-one"}, {"name": "legacy-two"}])
    monkeypatch.setattr("sqlit.shared.core.store.CONFIG_DIR", tmp_path)

    assert set(completion.complete_connection_names("")) == {"legacy-one", "legacy-two"}


def test_complete_connection_names_missing_file_is_safe(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("sqlit.shared.core.store.CONFIG_DIR", tmp_path / "nope")
    assert completion.complete_connection_names("") == []


def test_complete_connection_names_malformed_json_is_safe(tmp_path: Path, monkeypatch):
    (tmp_path).mkdir(parents=True, exist_ok=True)
    (tmp_path / "connections.json").write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr("sqlit.shared.core.store.CONFIG_DIR", tmp_path)
    assert completion.complete_connection_names("") == []


# --------------------------------------------------------------------------
# `sqlit completion <shell>` subcommand
# --------------------------------------------------------------------------


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_completion_subcommand_prints_script(shell: str):
    pytest.importorskip("argcomplete")
    result = subprocess.run(
        [sys.executable, "-m", "sqlit.cli", "completion", shell],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), "expected a non-empty completion script"
    assert "sqlit" in result.stdout


def test_completion_subcommand_rejects_unknown_shell():
    result = subprocess.run(
        [sys.executable, "-m", "sqlit.cli", "completion", "powershell"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "invalid choice" in result.stderr


# --------------------------------------------------------------------------
# End-to-end argcomplete protocol
# --------------------------------------------------------------------------


def _run_completion(comp_line: str, config_dir: Path) -> list[str]:
    """Drive the argcomplete protocol and return the emitted candidates.

    argcomplete writes the newline/IFS-separated candidates to fd 8, so we use
    a bash redirection (`8>file`) to capture them.
    """
    out_file = config_dir / "_comp_out"
    inner = f"exec {sys.executable!s} -m sqlit.cli 8>{out_file!s} 9>/dev/null 2>/dev/null"
    env = {
        **os.environ,
        "SQLIT_CONFIG_DIR": str(config_dir),
        "_ARGCOMPLETE": "1",
        "_ARGCOMPLETE_SHELL": "bash",
        "_ARGCOMPLETE_COMP_WORDBREAKS": " \t\n\"'><=;|&(:",
        "COMP_LINE": comp_line,
        "COMP_POINT": str(len(comp_line)),
        "COMP_TYPE": "9",
    }
    subprocess.run(["bash", "-c", inner], env=env)
    if not out_file.exists():
        return []
    raw = out_file.read_text(encoding="utf-8", errors="replace")
    # Candidates are separated by the IFS argcomplete uses (\013) or whitespace.
    parts = raw.replace("\013", "\n").split("\n")
    return [p.strip() for p in parts if p.strip()]


def test_argcomplete_completes_subcommands(tmp_path: Path):
    pytest.importorskip("argcomplete")
    candidates = _run_completion("sqlit ", tmp_path)
    for expected in ("connections", "connect", "query", "alerts", "completion"):
        assert expected in candidates, f"{expected!r} missing from {candidates}"


def test_argcomplete_completes_providers_for_connect(tmp_path: Path):
    pytest.importorskip("argcomplete")
    candidates = _run_completion("sqlit connect ", tmp_path)
    for expected in ("postgresql", "mysql", "sqlite"):
        assert expected in candidates


def test_argcomplete_completes_saved_connection_names(tmp_path: Path):
    pytest.importorskip("argcomplete")
    _write_connections(
        tmp_path,
        {"version": 2, "connections": [{"name": "prod-pg"}, {"name": "prod-mysql"}, {"name": "staging"}]},
    )
    candidates = _run_completion("sqlit query --connection prod", tmp_path)
    assert set(candidates) == {"prod-pg", "prod-mysql"}
