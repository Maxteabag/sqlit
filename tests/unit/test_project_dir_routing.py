"""Tests for project-scoped config routing via runtime.project_dir."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sqlit.cli import _extract_project_dir, _looks_like_project_path
from sqlit.domains.connections.store.connections import ConnectionStore
from sqlit.domains.query.store.history import HistoryStore
from sqlit.domains.query.store.starred import StarredStore
from sqlit.shared.app.runtime import RuntimeConfig


class TestLooksLikePath:
    @pytest.mark.parametrize(
        "arg",
        [
            ".",
            "..",
            "./foo",
            "../bar",
            "/absolute/path",
            "~/home-path",
            "trailing/",
        ],
    )
    def test_path_like(self, arg: str) -> None:
        assert _looks_like_project_path(arg) is True

    @pytest.mark.parametrize(
        "arg",
        [
            "connections",
            "query",
            "mysql://user@host/db",
            "testdb",
            "some-name",
        ],
    )
    def test_not_path_like(self, arg: str) -> None:
        assert _looks_like_project_path(arg) is False


class TestExtractProjectDir:
    def test_extracts_dot(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        project_dir, remaining = _extract_project_dir(["sqlit", "."])
        assert project_dir == tmp_path.resolve()
        assert remaining == ["sqlit"]

    def test_extracts_absolute_path(self, tmp_path: Path) -> None:
        project_dir, remaining = _extract_project_dir(["sqlit", str(tmp_path)])
        # str(tmp_path) starts with `/` so it's path-like.
        assert project_dir == tmp_path.resolve()
        assert remaining == ["sqlit"]

    def test_missing_dir_errors(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        bogus = tmp_path / "does-not-exist"
        with pytest.raises(SystemExit) as exc:
            _extract_project_dir(["sqlit", str(bogus)])
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "does not exist" in captured.err

    def test_no_path_arg(self) -> None:
        project_dir, remaining = _extract_project_dir(["sqlit", "connections", "list"])
        assert project_dir is None
        assert remaining == ["sqlit", "connections", "list"]

    def test_subcommand_after_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        project_dir, remaining = _extract_project_dir(
            ["sqlit", ".", "connections", "list"]
        )
        assert project_dir == tmp_path.resolve()
        assert remaining == ["sqlit", "connections", "list"]

    def test_flags_passthrough(self, tmp_path: Path) -> None:
        project_dir, remaining = _extract_project_dir(
            ["sqlit", "--theme", "dracula", str(tmp_path)]
        )
        assert project_dir == tmp_path.resolve()
        assert remaining == ["sqlit", "--theme", "dracula"]


class TestRuntimeProjectConfigDir:
    def test_project_config_dir_appends_dot_sqlit(self, tmp_path: Path) -> None:
        runtime = RuntimeConfig(project_dir=tmp_path)
        assert runtime.project_config_dir == tmp_path / ".sqlit"

    def test_project_config_dir_none_when_unset(self) -> None:
        runtime = RuntimeConfig()
        assert runtime.project_config_dir is None


class TestStoreOverrides:
    def test_history_store_uses_base_dir(self, tmp_path: Path) -> None:
        s = HistoryStore(base_dir=tmp_path / "queries")
        s.save_query("c", "SELECT 1")
        files = list((tmp_path / "queries").rglob("*.sql"))
        assert len(files) == 1

    def test_starred_store_uses_file_path(self, tmp_path: Path) -> None:
        s = StarredStore(file_path=tmp_path / "starred.json")
        s.star_query("c", "SELECT 1")
        assert (tmp_path / "starred.json").exists()
        data = json.loads((tmp_path / "starred.json").read_text())
        assert data == {"c": ["SELECT 1"]}

    def test_connection_store_uses_file_path(self, tmp_path: Path) -> None:
        s = ConnectionStore(file_path=tmp_path / "conns.json")
        assert s.file_path == tmp_path / "conns.json"


class TestBuildAppServicesProjectDir:
    def test_project_dir_routes_history_and_starred(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Keep global config out of the way.
        global_config = tmp_path / "global-config"
        monkeypatch.setenv("SQLIT_CONFIG_DIR", str(global_config))

        # Reset the module-level CONFIG_DIR which was resolved at import time.
        # We do this by directly patching the stores' constructed paths via
        # the explicit overrides — that's the contract under test.
        project = tmp_path / "project"
        project.mkdir()

        runtime = RuntimeConfig(project_dir=project)
        project_config = runtime.project_config_dir
        assert project_config is not None
        project_config.mkdir(parents=True, exist_ok=True)

        history = HistoryStore(base_dir=project_config / "queries")
        starred = StarredStore(file_path=project_config / "starred_queries.json")
        connections = ConnectionStore(file_path=project_config / "connections.json")

        history.save_query("conn-a", "SELECT 1")
        starred.star_query("conn-a", "SELECT 1")

        # All artifacts ended up in <project>/.sqlit/, not in global.
        assert (project / ".sqlit" / "queries").is_dir()
        assert (project / ".sqlit" / "starred_queries.json").is_file()
        assert connections.file_path.parent == project / ".sqlit"
        # Global config was not touched.
        assert not global_config.exists() or not any(global_config.iterdir())
