"""Fake system probe for tests and demos."""

from __future__ import annotations

from dataclasses import dataclass

from sqlit.shared.core.system_probe import SystemProbeProtocol


@dataclass
class FakeSystemProbe(SystemProbeProtocol):
    executable: str = "python"
    pip_available_value: bool = True
    user_site_enabled_value: bool = True
    install_paths_writable_value: bool = True
    in_venv_value: bool = False
    pep668_externally_managed_value: bool = False
    is_arch_linux_value: bool = False
    install_method: str | None = None

    @classmethod
    def from_probe(
        cls,
        probe: SystemProbeProtocol,
        *,
        install_method: str | None = None,
        pip_available: bool | None = None,
        user_site_enabled: bool | None = None,
        install_paths_writable: bool | None = None,
        in_venv: bool | None = None,
        pep668_externally_managed: bool | None = None,
        is_arch_linux: bool | None = None,
    ) -> FakeSystemProbe:
        return cls(
            executable=probe.executable,
            pip_available_value=probe.pip_available() if pip_available is None else pip_available,
            user_site_enabled_value=probe.user_site_enabled() if user_site_enabled is None else user_site_enabled,
            install_paths_writable_value=(
                probe.install_paths_writable() if install_paths_writable is None else install_paths_writable
            ),
            in_venv_value=probe.in_venv() if in_venv is None else in_venv,
            pep668_externally_managed_value=(
                probe.pep668_externally_managed()
                if pep668_externally_managed is None
                else pep668_externally_managed
            ),
            is_arch_linux_value=probe.is_arch_linux() if is_arch_linux is None else is_arch_linux,
            install_method=install_method if install_method is not None else probe.install_method_hint(),
        )

    def in_venv(self) -> bool:
        return self.in_venv_value

    def is_pipx(self) -> bool:
        return self.install_method == "pipx"

    def is_uvx(self) -> bool:
        return self.install_method == "uvx"

    def is_uv_run(self) -> bool:
        return self.install_method == "uv"

    def is_conda(self) -> bool:
        return self.install_method == "conda"

    def pep668_externally_managed(self) -> bool:
        return self.pep668_externally_managed_value

    def pip_available(self) -> bool:
        return self.pip_available_value

    def user_site_enabled(self) -> bool:
        return self.user_site_enabled_value

    def is_arch_linux(self) -> bool:
        return self.is_arch_linux_value

    def install_paths_writable(self) -> bool:
        return self.install_paths_writable_value

    def install_method_hint(self) -> str | None:
        return self.install_method
