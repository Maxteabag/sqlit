from __future__ import annotations

from sqlit.domains.connections.app.install_strategy import detect_strategy
from sqlit.shared.core.system_probe import SystemProbe


def test_detect_strategy_pipx_override():
    strategy = detect_strategy(
        extra_name="postgres",
        package_name="psycopg2-binary",
        mock_pipx="pipx",
    )
    assert strategy.kind == "pipx"
    assert strategy.can_auto_install is True
    assert strategy.auto_install_command == ["pipx", "inject", "sqlit-tui", "psycopg2-binary"]
    assert strategy.install_target == "psycopg2-binary"


def test_detect_strategy_externally_managed_disables_auto_install(tmp_path):
    marker_dir = tmp_path / "stdlib"
    marker_dir.mkdir()
    (marker_dir / "EXTERNALLY-MANAGED").write_text("managed", encoding="utf-8")

    probe = SystemProbe(
        env={},
        prefix="system",
        base_prefix="system",
        stdlib_paths=[str(marker_dir)],
        pip_available=True,
    )
    strategy = detect_strategy(extra_name="postgres", package_name="psycopg2-binary", probe=probe)
    assert strategy.kind == "externally-managed"
    assert strategy.can_auto_install is False
    assert "externally managed" in (strategy.reason_unavailable or "").lower()
    assert "pipx inject" in strategy.manual_instructions


def test_detect_strategy_pip_user_fallback(tmp_path):
    probe = SystemProbe(
        env={},
        prefix="system",
        base_prefix="system",
        pip_available=True,
        user_site_enabled=True,
        sysconfig_paths={"purelib": str(tmp_path / "purelib")},
        path_writable=lambda _path: False,
    )

    strategy = detect_strategy(extra_name="postgres", package_name="psycopg2-binary", probe=probe)
    assert strategy.kind == "pip-user"
    assert strategy.can_auto_install is True
    assert "--user" in (strategy.auto_install_command or [])
    assert (strategy.auto_install_command or [])[-1] == "sqlit-tui[postgres]"
