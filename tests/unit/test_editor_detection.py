"""Tests for terminal editor detection and preference resolution."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from sqlit.domains.query.app.editor import (
    build_editor_argv,
    detect_editors,
    env_default_editor,
    resolve_editor,
)


class TestDetectEditors:
    def test_returns_known_editors_with_resolved_paths(self) -> None:
        with patch("sqlit.domains.query.app.editor.shutil.which") as which:
            which.side_effect = lambda cmd: f"/usr/bin/{cmd}" if cmd in {"nvim", "nano"} else None
            entries = detect_editors()

        names = [e.command for e in entries]
        assert "nvim" in names
        assert "vim" in names

        nvim = next(e for e in entries if e.command == "nvim")
        vim = next(e for e in entries if e.command == "vim")
        assert nvim.is_installed
        assert nvim.path == "/usr/bin/nvim"
        assert not vim.is_installed
        assert vim.path is None


class TestEnvDefault:
    def test_uses_visual_first(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VISUAL", "nvim")
        monkeypatch.setenv("EDITOR", "vim")
        with patch(
            "sqlit.domains.query.app.editor.shutil.which",
            side_effect=lambda cmd: "/usr/bin/nvim" if cmd == "nvim" else None,
        ):
            assert env_default_editor() == "nvim"

    def test_falls_back_to_editor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("VISUAL", raising=False)
        monkeypatch.setenv("EDITOR", "vim")
        with patch(
            "sqlit.domains.query.app.editor.shutil.which",
            side_effect=lambda cmd: "/usr/bin/vim" if cmd == "vim" else None,
        ):
            assert env_default_editor() == "vim"

    def test_strips_args_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("VISUAL", raising=False)
        monkeypatch.setenv("EDITOR", "code -w")
        with patch(
            "sqlit.domains.query.app.editor.shutil.which",
            side_effect=lambda cmd: "/usr/local/bin/code" if cmd == "code" else None,
        ):
            assert env_default_editor() == "code"

    def test_none_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("VISUAL", raising=False)
        monkeypatch.delenv("EDITOR", raising=False)
        assert env_default_editor() is None

    def test_none_when_env_editor_missing_on_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EDITOR", "made-up-editor")
        with patch("sqlit.domains.query.app.editor.shutil.which", return_value=None):
            assert env_default_editor() is None


class TestResolveEditor:
    def test_uses_preferred_when_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("VISUAL", raising=False)
        monkeypatch.delenv("EDITOR", raising=False)
        with patch(
            "sqlit.domains.query.app.editor.shutil.which",
            side_effect=lambda cmd: "/usr/bin/hx" if cmd == "hx" else None,
        ):
            assert resolve_editor("hx") == "hx"

    def test_falls_back_to_env_when_preferred_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EDITOR", "vim")

        def which(cmd: str) -> str | None:
            return "/usr/bin/vim" if cmd == "vim" else None

        with patch("sqlit.domains.query.app.editor.shutil.which", side_effect=which):
            # preferred "hx" not installed → falls back to $EDITOR
            assert resolve_editor("hx") == "vim"

    def test_none_when_nothing_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("VISUAL", raising=False)
        monkeypatch.delenv("EDITOR", raising=False)
        with patch("sqlit.domains.query.app.editor.shutil.which", return_value=None):
            assert resolve_editor(None) is None


class TestBuildEditorArgv:
    def test_default_is_just_command(self) -> None:
        assert build_editor_argv("nvim") == ["nvim"]
        assert build_editor_argv("vim") == ["vim"]

    def test_emacs_gets_nw_flag(self) -> None:
        # emacs without -nw spawns a GUI window — we want terminal mode.
        assert build_editor_argv("emacs") == ["emacs", "-nw"]
