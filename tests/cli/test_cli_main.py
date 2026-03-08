from __future__ import annotations

from pathlib import Path

from tests.conftest import run_cli


def test_cli_connections_list_empty(tmp_path: Path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"allow_plaintext_credentials": true}', encoding="utf-8")

    monkeypatch.setenv("SQLIT_CONFIG_DIR", str(tmp_path))

    result = run_cli("connections", "list", check=False)

    assert result.returncode == 0
    assert "No saved connections." in result.stdout
