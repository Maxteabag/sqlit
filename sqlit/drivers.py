"""ODBC Driver detection and installation helpers."""

from __future__ import annotations

import platform
from dataclasses import dataclass, field

# In order of preference
SUPPORTED_DRIVERS = [
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "ODBC Driver 13 for SQL Server",
    "ODBC Driver 11 for SQL Server",
    "SQL Server Native Client 11.0",
    "SQL Server",
]

# Supported OS versions per Microsoft documentation (2024-2025)
SUPPORTED_VERSIONS = {
    "ubuntu": ["18.04", "20.04", "22.04", "24.04", "24.10"],
    "debian": ["9", "10", "11", "12"],
    "rhel": ["7", "8", "9"],
    "oracle": ["7", "8", "9"],
    "sles": ["12", "15"],
    "alpine": ["3.17", "3.18", "3.19", "3.20"],
}


@dataclass
class InstallCommand:
    """Installation command for a specific OS."""

    description: str
    commands: list[str]
    requires_sudo: bool = True
    warnings: list[str] = field(default_factory=list)


def get_installed_drivers() -> list[str]:
    """Get list of installed ODBC drivers for SQL Server."""
    installed = []

    try:
        import pyodbc

        available = list(pyodbc.drivers())
        for driver in SUPPORTED_DRIVERS:
            if driver in available:
                installed.append(driver)
    except ImportError:
        pass

    return installed


def get_best_driver() -> str | None:
    """Get the best available driver, or None if none installed."""
    installed = get_installed_drivers()
    return installed[0] if installed else None


def get_os_info() -> tuple[str, str]:
    """Get OS type and version."""
    system = platform.system().lower()

    if system == "linux":
        try:
            with open("/etc/os-release") as f:
                info = {}
                for line in f:
                    if "=" in line:
                        key, value = line.strip().split("=", 1)
                        info[key] = value.strip('"')
                distro = info.get("ID", "unknown")
                version = info.get("VERSION_ID", "")
                return distro, version
        except FileNotFoundError:
            return "linux", ""
    elif system == "darwin":
        return "macos", platform.mac_ver()[0]
    elif system == "windows":
        return "windows", platform.version()

    return system, ""


def _check_version_support(os_type: str, version: str) -> list[str]:
    """Check if the OS version is officially supported and return warnings if not."""
    warnings = []
    supported = SUPPORTED_VERSIONS.get(os_type)

    if supported and version:
        # For distros that use major version only
        major_version = version.split(".")[0]
        if version not in supported and major_version not in supported:
            warnings.append(
                f"Warning: {os_type} {version} may not be officially supported. "
                f"Supported versions: {', '.join(supported)}"
            )
    return warnings


def get_install_commands(driver: str = "ODBC Driver 18 for SQL Server") -> InstallCommand | None:
    """Get installation commands for the current OS.

    Commands are based on Microsoft's official documentation:
    https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server
    """
    os_type, os_version = get_os_info()
    driver_pkg = "msodbcsql18" if "18" in driver else "msodbcsql17"

    if os_type == "macos":
        return InstallCommand(
            description="Install via Homebrew",
            commands=[
                "brew install unixodbc",
                "brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release",
                "brew update",
                f"HOMEBREW_ACCEPT_EULA=Y brew install {driver_pkg}",
            ],
            requires_sudo=False,
        )

    elif os_type == "ubuntu":
        version = os_version or "22.04"
        warnings = _check_version_support("ubuntu", version)
        return InstallCommand(
            description=f"Install on Ubuntu {version}",
            commands=[
                f"curl -sSL -O https://packages.microsoft.com/config/ubuntu/{version}/packages-microsoft-prod.deb",
                "sudo dpkg -i packages-microsoft-prod.deb",
                "rm packages-microsoft-prod.deb",
                "sudo apt-get update",
                f"sudo ACCEPT_EULA=Y apt-get install -y {driver_pkg}",
            ],
            warnings=warnings,
        )

    elif os_type == "debian":
        version = os_version.split(".")[0] if os_version else "12"
        warnings = _check_version_support("debian", version)
        return InstallCommand(
            description=f"Install on Debian {version}",
            commands=[
                f"curl -sSL -O https://packages.microsoft.com/config/debian/{version}/packages-microsoft-prod.deb",
                "sudo dpkg -i packages-microsoft-prod.deb",
                "rm packages-microsoft-prod.deb",
                "sudo apt-get update",
                f"sudo ACCEPT_EULA=Y apt-get install -y {driver_pkg}",
            ],
            warnings=warnings,
        )

    elif os_type == "fedora":
        # Fedora uses RHEL 9 packages
        return InstallCommand(
            description="Install on Fedora (using RHEL 9 packages)",
            commands=[
                "curl -sSL -O https://packages.microsoft.com/config/rhel/9/packages-microsoft-prod.rpm",
                "sudo rpm -i packages-microsoft-prod.rpm",
                "rm packages-microsoft-prod.rpm",
                "sudo dnf remove -y unixODBC-utf16 unixODBC-utf16-devel 2>/dev/null || true",
                f"sudo ACCEPT_EULA=Y dnf install -y {driver_pkg}",
            ],
        )

    elif os_type in ("rhel", "centos", "rocky", "almalinux"):
        version = os_version.split(".")[0] if os_version else "9"
        warnings = _check_version_support("rhel", version)
        return InstallCommand(
            description=f"Install on {os_type.upper()} {version}",
            commands=[
                f"curl -sSL -O https://packages.microsoft.com/config/rhel/{version}/packages-microsoft-prod.rpm",
                "sudo rpm -i packages-microsoft-prod.rpm",
                "rm packages-microsoft-prod.rpm",
                "sudo yum remove -y unixODBC-utf16 unixODBC-utf16-devel 2>/dev/null || true",
                f"sudo ACCEPT_EULA=Y yum install -y {driver_pkg}",
            ],
            warnings=warnings,
        )

    elif os_type == "ol":  # Oracle Linux
        version = os_version.split(".")[0] if os_version else "9"
        warnings = _check_version_support("oracle", version)
        return InstallCommand(
            description=f"Install on Oracle Linux {version}",
            commands=[
                f"curl -sSL -O https://packages.microsoft.com/config/rhel/{version}/packages-microsoft-prod.rpm",
                "sudo rpm -i packages-microsoft-prod.rpm",
                "rm packages-microsoft-prod.rpm",
                "sudo yum remove -y unixODBC-utf16 unixODBC-utf16-devel 2>/dev/null || true",
                f"sudo ACCEPT_EULA=Y yum install -y {driver_pkg}",
            ],
            warnings=warnings,
        )

    elif os_type in ("sles", "opensuse-leap"):
        version = os_version.split(".")[0] if os_version else "15"
        warnings = _check_version_support("sles", version)
        return InstallCommand(
            description=f"Install on SLES/openSUSE {version}",
            commands=[
                "sudo rpm --import https://packages.microsoft.com/keys/microsoft.asc",
                f"curl -sSL -O https://packages.microsoft.com/config/sles/{version}/packages-microsoft-prod.rpm",
                "sudo zypper install -y packages-microsoft-prod.rpm",
                "rm packages-microsoft-prod.rpm",
                "sudo zypper refresh",
                f"sudo ACCEPT_EULA=Y zypper install -y {driver_pkg}",
            ],
            warnings=warnings,
        )

    elif os_type == "alpine":
        version = os_version or "3.20"
        warnings = _check_version_support("alpine", version)
        # Alpine requires direct package download
        arch = "amd64" if platform.machine() == "x86_64" else "arm64"
        return InstallCommand(
            description=f"Install on Alpine Linux {version}",
            commands=[
                f"curl -O https://download.microsoft.com/download/fae28b9a-d880-42fd-9b98-d779f0fdd77f/{driver_pkg}_18.5.1.1-1_{arch}.apk",
                f"sudo apk add --allow-untrusted {driver_pkg}_18.5.1.1-1_{arch}.apk",
            ],
            warnings=warnings + ["Note: Alpine package URLs may change with new driver versions"],
        )

    elif os_type == "arch":
        return InstallCommand(
            description="Install on Arch Linux (AUR)",
            commands=[
                "yay -S msodbcsql",
            ],
            requires_sudo=False,
            warnings=["Alternative AUR helpers: paru -S msodbcsql"],
        )

    elif os_type == "windows":
        winget_pkg = "Microsoft.msodbcsql.17" if "17" in driver else "Microsoft.msodbcsql.18"
        return InstallCommand(
            description="Install via winget",
            commands=[
                f"winget install {winget_pkg}",
            ],
            requires_sudo=False,
            warnings=[
                "Alternative: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server"
            ],
        )

    return None


def run_install_in_terminal(driver: str = "ODBC Driver 18 for SQL Server") -> tuple[bool, str]:
    """Run driver installation commands in a new terminal window.

    Returns (success, message) tuple.
    """
    from .terminal import TerminalType, run_in_terminal

    install_cmd = get_install_commands(driver)
    if not install_cmd:
        os_type, _ = get_os_info()
        return False, f"No installation commands available for {os_type}"

    result = run_in_terminal(install_cmd.commands)

    if not result.success:
        if result.terminal == TerminalType.NONE:
            cmd_str = " && ".join(install_cmd.commands)
            return False, f"No terminal found. Run manually:\n{cmd_str}"
        return False, f"Failed to launch terminal: {result.error}"

    return True, "Installation started in new terminal. Restart sqlit when done."
