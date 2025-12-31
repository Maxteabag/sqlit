"""Detection for how sqlit-tui should suggest/install optional Python drivers.

This module intentionally avoids depending on Textual or other app layers so it
can be used from adapters, services, and UI screens.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlit.shared.core.system_probe import SystemProbe


@dataclass(frozen=True)
class InstallStrategy:
    """Represents how to install optional Python dependencies for the running app."""

    kind: str
    can_auto_install: bool
    manual_instructions: str
    install_target: str | None = None
    auto_install_command: list[str] | None = None
    reason_unavailable: str | None = None


def _normalize_install_kind(kind: str) -> str:
    return "pip" if kind == "pip-user" else kind


def _format_shell_target(target: str) -> str:
    if any(ch in target for ch in (" ", "[", "]")):
        return f"\"{target}\""
    return target


def _install_target_for_method(method: str, *, package_name: str, extra_name: str | None) -> str:
    if extra_name and method in {"pip", "uv", "poetry", "pdm"}:
        return f"sqlit-tui[{extra_name}]"
    return package_name


def _install_target_for_kind(kind: str, *, package_name: str, extra_name: str | None) -> str:
    return _install_target_for_method(
        _normalize_install_kind(kind),
        package_name=package_name,
        extra_name=extra_name,
    )


def _is_pipx(mock_pipx: str | None, probe: SystemProbe) -> bool:
    pipx_override = (mock_pipx or "").strip().lower()
    if pipx_override in {"1", "true", "yes", "pipx"}:
        return True
    if pipx_override in {"0", "false", "no", "pip", "unknown", "no-pip", "uvx", "conda", "uv"}:
        return False

    return probe.is_pipx()


def _is_uvx(mock_pipx: str | None, probe: SystemProbe) -> bool:
    """Check if running via uvx or uv tool install."""
    mock = (mock_pipx or "").strip().lower()
    if mock == "uvx":
        return True
    if mock in {"pipx", "pip", "conda", "uv"}:
        return False

    return probe.is_uvx()


def _is_uv_run(mock_pipx: str | None, probe: SystemProbe) -> bool:
    """Check if running via uv run (uv-managed project environment)."""
    mock = (mock_pipx or "").strip().lower()
    if mock == "uv":
        return True
    if mock in {"pipx", "pip", "conda", "uvx"}:
        return False

    return probe.is_uv_run()


def _is_conda(mock_pipx: str | None, probe: SystemProbe) -> bool:
    """Check if running in a conda environment."""
    mock = (mock_pipx or "").strip().lower()
    if mock == "conda":
        return True
    if mock in {"pipx", "pip", "uvx"}:
        return False

    return probe.is_conda()


def _is_unknown_install(mock_pipx: str | None) -> bool:
    """Check if we should mock an unknown installation method (e.g., uvx)."""
    return (mock_pipx or "").strip().lower() == "unknown"


def _pep668_externally_managed(probe: SystemProbe) -> bool:
    return probe.pep668_externally_managed()


def _pip_available(mock_no_pip: bool, mock_pipx: str | None, probe: SystemProbe) -> bool:
    if mock_no_pip or (mock_pipx or "").strip().lower() == "no-pip":
        return False
    return probe.pip_available()


def _user_site_enabled(probe: SystemProbe) -> bool:
    return probe.user_site_enabled()


def _is_arch_linux(probe: SystemProbe) -> bool:
    """Check if running on Arch Linux or derivative."""
    return probe.is_arch_linux()


def _install_paths_writable(probe: SystemProbe) -> bool:
    return probe.install_paths_writable()


def _get_arch_package_name(package_name: str) -> str | None:
    """Map PyPI package name to Arch Linux package name."""
    mapping = {
        "psycopg2-binary": "python-psycopg2",
        "psycopg2": "python-psycopg2",
        "mssql-python": "python-mssql",
        "mysql-connector-python": "python-mysql-connector",
        "mariadb": "python-mariadb-connector",
        "oracledb": "python-oracledb",
        "duckdb": "python-duckdb",
        "clickhouse-connect": "python-clickhouse-connect",
        "snowflake-connector-python": "python-snowflake-connector-python",
        "requests": "python-requests",
        "paramiko": "python-paramiko",
        "sshtunnel": "python-sshtunnel",
    }
    return mapping.get(package_name)


@dataclass(frozen=True)
class InstallOption:
    """A single install option with label and command."""

    label: str
    command: str


def detect_install_method(*, mock_pipx: str | None = None, probe: SystemProbe | None = None) -> str:
    """Detect how sqlit was installed/is running.

    Returns one of: 'pipx', 'uvx', 'uv', 'conda', 'pip'.
    'pipx', 'uvx', 'uv' (uv run), and 'conda' are high-confidence detections.
    """
    probe = probe or SystemProbe()

    # Check high-confidence detections first (runtime environment)
    if _is_pipx(mock_pipx, probe):
        return "pipx"
    if _is_uvx(mock_pipx, probe):
        return "uvx"
    if _is_uv_run(mock_pipx, probe):
        return "uv"
    if _is_conda(mock_pipx, probe):
        return "conda"

    # Default to pip (most common)
    return "pip"


def get_install_options(
    *,
    package_name: str,
    extra_name: str | None,
    mock_pipx: str | None = None,
    probe: SystemProbe | None = None,
) -> list[InstallOption]:
    """Get list of install options for a package, ordered by detected install method."""
    probe = probe or SystemProbe()

    def target_for(method: str) -> str:
        return _install_target_for_method(method, package_name=package_name, extra_name=extra_name)

    def shell_target(method: str) -> str:
        return _format_shell_target(target_for(method))

    # All available options
    all_options = {
        "pip": InstallOption("pip", f"pip install {shell_target('pip')}"),
        "pipx": InstallOption("pipx", f"pipx inject sqlit-tui {shell_target('pipx')}"),
        "uv": InstallOption("uv", f"uv pip install {shell_target('uv')}"),
        "uvx": InstallOption("uvx", f"uvx --with {shell_target('uvx')} sqlit-tui"),
        "poetry": InstallOption("poetry", f"poetry add {shell_target('poetry')}"),
        "pdm": InstallOption("pdm", f"pdm add {shell_target('pdm')}"),
        "conda": InstallOption("conda", f"conda install {shell_target('conda')}"),
    }

    # Detect install method and set preferred order
    detected = detect_install_method(mock_pipx=mock_pipx, probe=probe)

    # Order based on detection - detected method first, then common alternatives
    if detected == "pipx":
        order = ["pipx", "pip", "uv", "uvx", "poetry", "pdm", "conda"]
    elif detected == "uvx":
        order = ["uvx", "uv", "pip", "pipx", "poetry", "pdm", "conda"]
    elif detected == "uv":
        # uv run - prefer uv pip install
        order = ["uv", "pip", "uvx", "pipx", "poetry", "pdm", "conda"]
    elif detected == "conda":
        order = ["conda", "pip", "uv", "pipx", "uvx", "poetry", "pdm"]
    else:
        # Default: pip first
        order = ["pip", "uv", "pipx", "uvx", "poetry", "pdm", "conda"]

    options = [all_options[key] for key in order]

    # Add Arch Linux options at the end if on Arch
    if _is_arch_linux(probe):
        arch_pkg = _get_arch_package_name(package_name)
        if arch_pkg:
            options.append(InstallOption("pacman", f"pacman -S {arch_pkg}"))
            options.append(InstallOption("yay", f"yay -S {arch_pkg}"))

    return options


def _format_manual_instructions(
    *,
    package_name: str,
    extra_name: str | None,
    reason: str,
    mock_pipx: str | None = None,
    probe: SystemProbe | None = None,
) -> str:
    """Format manual installation instructions with rich markup."""
    lines = [
        f"{reason}\n",
        "[bold]Install the driver using your preferred package manager:[/]\n",
    ]
    for opt in get_install_options(
        package_name=package_name,
        extra_name=extra_name,
        mock_pipx=mock_pipx,
        probe=probe,
    ):
        lines.append(f"  [cyan]{opt.label}[/]     {opt.command}")

    return "\n".join(lines)


def detect_strategy(
    *,
    extra_name: str,
    package_name: str,
    mock_pipx: str | None = None,
    mock_no_pip: bool = False,
    mock_driver_error: bool = False,
    probe: SystemProbe | None = None,
) -> InstallStrategy:
    """Detect the best installation strategy for optional driver dependencies."""
    probe = probe or SystemProbe()

    # When mocking driver errors, also force the no-pip path to show full instructions
    if mock_driver_error:
        install_target = _install_target_for_kind("pip", package_name=package_name, extra_name=extra_name)
        return InstallStrategy(
            kind="no-pip",
            can_auto_install=False,
            manual_instructions=_format_manual_instructions(
                package_name=package_name,
                extra_name=extra_name,
                reason="pip is not available for this Python interpreter.",
                mock_pipx=mock_pipx,
                probe=probe,
            ),
            reason_unavailable="pip is not available.",
            install_target=install_target,
        )

    if _is_unknown_install(mock_pipx):
        install_target = _install_target_for_kind("pip", package_name=package_name, extra_name=extra_name)
        return InstallStrategy(
            kind="unknown",
            can_auto_install=False,
            manual_instructions=_format_manual_instructions(
                package_name=package_name,
                extra_name=extra_name,
                reason="Unable to detect how sqlit was installed.",
                mock_pipx=mock_pipx,
                probe=probe,
            ),
            reason_unavailable="Unable to detect installation method.",
            install_target=install_target,
        )

    if _is_pipx(mock_pipx, probe):
        install_target = _install_target_for_kind("pipx", package_name=package_name, extra_name=extra_name)
        cmd = ["pipx", "inject", "sqlit-tui", install_target]
        return InstallStrategy(
            kind="pipx",
            can_auto_install=True,
            manual_instructions="pipx inject sqlit-tui " + _format_shell_target(install_target),
            auto_install_command=cmd,
            install_target=install_target,
        )

    if _pep668_externally_managed(probe):
        install_target = _install_target_for_kind("pip", package_name=package_name, extra_name=extra_name)
        return InstallStrategy(
            kind="externally-managed",
            can_auto_install=False,
            manual_instructions=_format_manual_instructions(
                package_name=package_name,
                extra_name=extra_name,
                reason="This Python environment is externally managed (PEP 668).",
                mock_pipx=mock_pipx,
                probe=probe,
            ),
            reason_unavailable="Externally managed Python environment (PEP 668).",
            install_target=install_target,
        )

    if not _pip_available(mock_no_pip, mock_pipx, probe):
        install_target = _install_target_for_kind("pip", package_name=package_name, extra_name=extra_name)
        return InstallStrategy(
            kind="no-pip",
            can_auto_install=False,
            manual_instructions=_format_manual_instructions(
                package_name=package_name,
                extra_name=extra_name,
                reason="pip is not available for this Python interpreter.",
                mock_pipx=mock_pipx,
                probe=probe,
            ),
            reason_unavailable="pip is not available.",
            install_target=install_target,
        )

    pip_cmd = [probe.executable, "-m", "pip", "install"]
    if probe.in_venv() or _install_paths_writable(probe):
        install_target = _install_target_for_kind("pip", package_name=package_name, extra_name=extra_name)
        cmd = [*pip_cmd, install_target]
        return InstallStrategy(
            kind="pip",
            can_auto_install=True,
            manual_instructions=f"{probe.executable} -m pip install {_format_shell_target(install_target)}",
            auto_install_command=cmd,
            install_target=install_target,
        )

    if _user_site_enabled(probe):
        install_target = _install_target_for_kind("pip", package_name=package_name, extra_name=extra_name)
        cmd = [*pip_cmd, "--user", install_target]
        return InstallStrategy(
            kind="pip-user",
            can_auto_install=True,
            manual_instructions=f"{probe.executable} -m pip install --user {_format_shell_target(install_target)}",
            auto_install_command=cmd,
            install_target=install_target,
        )

    install_target = _install_target_for_kind("pip", package_name=package_name, extra_name=extra_name)
    return InstallStrategy(
        kind="pip-unwritable",
        can_auto_install=False,
        manual_instructions=_format_manual_instructions(
            package_name=package_name,
            extra_name=extra_name,
            reason="This Python environment is not writable and user-site installs are disabled.",
            mock_pipx=mock_pipx,
            probe=probe,
        ),
        reason_unavailable="Python environment not writable and user-site disabled.",
        install_target=install_target,
    )
