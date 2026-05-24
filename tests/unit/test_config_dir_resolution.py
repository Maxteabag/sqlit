"""Tests for config directory resolution and the one-time legacy migration."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point `Path.home()` at a tmpdir and clear env vars that matter."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("SQLIT_CONFIG_DIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return tmp_path


def _resolve() -> Path:
    # Re-import so the module-level LEGACY_CONFIG_DIR constant picks up
    # the current HOME, and _resolve_config_dir runs against the active env.
    from sqlit.shared.core import store

    importlib.reload(store)
    return store.CONFIG_DIR


def test_sqlit_config_dir_env_wins_and_skips_migration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = _isolated_home(monkeypatch, tmp_path)
    legacy = home / ".sqlit"
    legacy.mkdir()
    (legacy / "settings.json").write_text("{}")
    override = tmp_path / "custom-config"
    monkeypatch.setenv("SQLIT_CONFIG_DIR", str(override))

    resolved = _resolve()

    assert resolved == override
    # Legacy is untouched — explicit override means "don't migrate, use this."
    assert legacy.exists()
    assert (legacy / "settings.json").exists()


def test_xdg_config_home_is_respected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _isolated_home(monkeypatch, tmp_path)
    xdg = tmp_path / "xdg-conf"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))

    resolved = _resolve()

    assert resolved == xdg / "sqlit"


def test_default_path_without_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = _isolated_home(monkeypatch, tmp_path)

    resolved = _resolve()

    assert resolved == home / ".config" / "sqlit"


def test_migrates_legacy_into_new_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = _isolated_home(monkeypatch, tmp_path)
    legacy = home / ".sqlit"
    legacy.mkdir()
    (legacy / "settings.json").write_text('{"migrated": true}')
    (legacy / "themes").mkdir()
    (legacy / "themes" / "custom.json").write_text("{}")

    resolved = _resolve()

    assert resolved == home / ".config" / "sqlit"
    assert resolved.exists()
    assert not legacy.exists(), "legacy directory should be renamed away"
    assert (resolved / "settings.json").read_text() == '{"migrated": true}'
    assert (resolved / "themes" / "custom.json").exists()


def test_migration_skipped_when_new_path_has_core_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = _isolated_home(monkeypatch, tmp_path)
    legacy = home / ".sqlit"
    legacy.mkdir()
    (legacy / "settings.json").write_text('{"source": "legacy"}')
    new_path = home / ".config" / "sqlit"
    new_path.mkdir(parents=True)
    (new_path / "settings.json").write_text('{"source": "new"}')

    resolved = _resolve()

    assert resolved == new_path
    # Both still present — no clobber of user-edited files on either side.
    assert legacy.exists()
    assert (legacy / "settings.json").read_text() == '{"source": "legacy"}'
    assert (new_path / "settings.json").read_text() == '{"source": "new"}'


def test_merges_legacy_into_cache_only_new_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """New path created incidentally by cloud-discovery caches must not
    block the real migration."""
    home = _isolated_home(monkeypatch, tmp_path)
    legacy = home / ".sqlit"
    legacy.mkdir()
    (legacy / "settings.json").write_text('{"ok": true}')
    (legacy / "connections.json").write_text("[]")
    new_path = home / ".config" / "sqlit"
    new_path.mkdir(parents=True)
    (new_path / "aws_cache.json").write_text('{"cache": true}')

    resolved = _resolve()

    assert resolved == new_path
    assert (new_path / "settings.json").read_text() == '{"ok": true}'
    assert (new_path / "connections.json").read_text() == "[]"
    # Cache file left untouched.
    assert (new_path / "aws_cache.json").read_text() == '{"cache": true}'
    # Legacy fully drained and removed.
    assert not legacy.exists()


def test_merge_skips_entries_that_already_exist_in_new_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = _isolated_home(monkeypatch, tmp_path)
    legacy = home / ".sqlit"
    legacy.mkdir()
    (legacy / "aws_cache.json").write_text('{"from": "legacy"}')
    (legacy / "query_history.json").write_text('{"from": "legacy"}')
    new_path = home / ".config" / "sqlit"
    new_path.mkdir(parents=True)
    (new_path / "aws_cache.json").write_text('{"from": "new"}')

    resolved = _resolve()

    assert resolved == new_path
    # Same-named file in destination is preserved.
    assert (new_path / "aws_cache.json").read_text() == '{"from": "new"}'
    # Non-conflicting legacy file migrated in.
    assert (new_path / "query_history.json").read_text() == '{"from": "legacy"}'
    # Legacy still exists because one entry stayed behind.
    assert legacy.exists()
    assert (legacy / "aws_cache.json").exists()
    assert not (legacy / "query_history.json").exists()


def test_no_side_effects_when_neither_path_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = _isolated_home(monkeypatch, tmp_path)

    resolved = _resolve()

    assert resolved == home / ".config" / "sqlit"
    # Resolution must be pure lookup when there's nothing to migrate —
    # no directories created (stores do that lazily on first write).
    assert not resolved.exists()
    assert not (home / ".sqlit").exists()
