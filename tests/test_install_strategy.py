from __future__ import annotations

from sqlit.install_strategy import detect_strategy


def test_detect_strategy_pipx_override(monkeypatch):
    monkeypatch.setenv("SQLIT_MOCK_PIPX", "pipx")
    strategy = detect_strategy(extra_name="postgres", package_name="psycopg2-binary")
    assert strategy.kind == "pipx"
    assert strategy.can_auto_install is True
    assert strategy.auto_install_command == ["pipx", "inject", "sqlit-tui", "psycopg2-binary"]


def test_detect_strategy_externally_managed_disables_auto_install(monkeypatch, tmp_path):
    marker_dir = tmp_path / "stdlib"
    marker_dir.mkdir()
    (marker_dir / "EXTERNALLY-MANAGED").write_text("managed", encoding="utf-8")

    monkeypatch.delenv("SQLIT_MOCK_PIPX", raising=False)
    monkeypatch.setattr("sqlit.install_strategy._in_venv", lambda: False)
    monkeypatch.setattr("sqlit.install_strategy.sysconfig.get_path", lambda _key: str(marker_dir))

    strategy = detect_strategy(extra_name="postgres", package_name="psycopg2-binary")
    assert strategy.kind == "externally-managed"
    assert strategy.can_auto_install is False
    assert "externally managed" in (strategy.reason_unavailable or "").lower()
    assert "pipx inject" in strategy.manual_instructions


def test_detect_strategy_pip_user_fallback(monkeypatch):
    monkeypatch.delenv("SQLIT_MOCK_PIPX", raising=False)
    monkeypatch.setattr("sqlit.install_strategy._in_venv", lambda: False)
    monkeypatch.setattr("sqlit.install_strategy._pep668_externally_managed", lambda: False)
    monkeypatch.setattr("sqlit.install_strategy._pip_available", lambda: True)
    monkeypatch.setattr("sqlit.install_strategy._install_paths_writable", lambda: False)
    monkeypatch.setattr("sqlit.install_strategy._user_site_enabled", lambda: True)

    strategy = detect_strategy(extra_name="postgres", package_name="psycopg2-binary")
    assert strategy.kind == "pip-user"
    assert strategy.can_auto_install is True
    assert "--user" in (strategy.auto_install_command or [])
