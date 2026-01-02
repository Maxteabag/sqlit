"""Detection for how sqlit-tui should suggest/install optional Python drivers.

This module intentionally avoids depending on Textual or other app layers so it
can be used from adapters, services, and UI screens.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlit.shared.core.system_probe import SystemProbe, SystemProbeProtocol


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


def _install_method_hint(probe: SystemProbeProtocol) -> str | None:
    hint = probe.install_method_hint()
    if not hint:
        return None
    value = hint.strip().lower()
    return value or None


def _pep668_externally_managed(probe: SystemProbeProtocol) -> bool:
    return probe.pep668_externally_managed()


def _user_site_enabled(probe: SystemProbeProtocol) -> bool:
    return probe.user_site_enabled()


def _is_arch_linux(probe: SystemProbeProtocol) -> bool:
    """Check if running on Arch Linux or derivative."""
    return probe.is_arch_linux()


def _install_paths_writable(probe: SystemProbeProtocol) -> bool:
    return probe.install_paths_writable()


def _get_arch_package_name(package_name: str) -> str | None:
    """Map PyPI package name to Arch Linux package name."""
    mapping = {
        "psycopg2-binary": "python-psycopg2",
        "psycopg2": "python-psycopg2",
        "mssql-python": "python-mssql",
        "PyMySQL": "python-pymysql",
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


def detect_install_method(*, probe: SystemProbeProtocol | None = None) -> str:
    """Detect how sqlit was installed/is running.

    Returns one of: 'pipx', 'uvx', 'uv', 'conda', 'pip', or 'unknown'.
    'pipx', 'uvx', 'uv' (uv run), and 'conda' are high-confidence detections.
    """
    probe = probe or SystemProbe()

    hint = _install_method_hint(probe)
    if hint in {"pipx", "uvx", "uv", "conda", "pip", "unknown"}:
        return hint

    # Check high-confidence detections first (runtime environment)
    if probe.is_pipx():
        return "pipx"
    if probe.is_uvx():
        return "uvx"
    if probe.is_uv_run():
        return "uv"
    if probe.is_conda():
        return "conda"

    # Default to pip (most common)
    return "pip"


def get_install_options(
    *,
    package_name: str,
    extra_name: str | None,
    probe: SystemProbeProtocol | None = None,
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
    detected = detect_install_method(probe=probe)

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
    probe: SystemProbeProtocol | None = None,
) -> str:
    """Format manual installation instructions with rich markup."""
    lines = [
        f"{reason}\n",
        "[bold]Install the driver using your preferred package manager:[/]\n",
    ]
    for opt in get_install_options(
        package_name=package_name,
        extra_name=extra_name,
        probe=probe,
    ):
        lines.append(f"  [cyan]{opt.label}[/]     {opt.command}")

    return "\n".join(lines)


def detect_strategy(
    *,
    extra_name: str,
    package_name: str,
    probe: SystemProbeProtocol | None = None,
) -> InstallStrategy:
    """Detect the best installation strategy for optional driver dependencies."""
    probe = probe or SystemProbe()

    install_method = detect_install_method(probe=probe)
    if install_method == "unknown":
        install_target = _install_target_for_kind("pip", package_name=package_name, extra_name=extra_name)
        return InstallStrategy(
            kind="unknown",
            can_auto_install=False,
            manual_instructions=_format_manual_instructions(
                package_name=package_name,
                extra_name=extra_name,
                reason="Unable to detect how sqlit was installed.",
                probe=probe,
            ),
            reason_unavailable="Unable to detect installation method.",
            install_target=install_target,
        )

    if install_method == "pipx":
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
                probe=probe,
            ),
            reason_unavailable="Externally managed Python environment (PEP 668).",
            install_target=install_target,
        )

    if not probe.pip_available():
        install_target = _install_target_for_kind("pip", package_name=package_name, extra_name=extra_name)
        return InstallStrategy(
            kind="no-pip",
            can_auto_install=False,
            manual_instructions=_format_manual_instructions(
                package_name=package_name,
                extra_name=extra_name,
                reason="pip is not available for this Python interpreter.",
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
            probe=probe,
        ),
        reason_unavailable="Python environment not writable and user-site disabled.",
        install_target=install_target,
    )
