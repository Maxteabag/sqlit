"""Driver status formatting helpers for the connection screen."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from rich.markup import escape


class InstallStrategyResolver(Protocol):
    def detect(self, *, extra_name: str, package_name: str) -> Any: ...


@dataclass(frozen=True)
class DriverStatusDisplay:
    message: str
    subtitle: str
    success: bool = False


def _format_install_target(target: str) -> str:
    if any(ch in target for ch in (" ", "[", "]")):
        return f"\"{target}\""
    return target


def _format_install_hint(strategy: Any) -> str:
    target = str(getattr(strategy, "install_target", "") or "")
    target_hint = _format_install_target(target) if target else ""
    if strategy.kind == "pip":
        return f"pip install {target_hint}".strip()
    if strategy.kind == "pip-user":
        return f"pip install --user {target_hint}".strip()
    if strategy.kind == "pipx":
        return f"pipx inject sqlit-tui {target_hint}".strip()
    manual = getattr(strategy, "manual_instructions", "")
    if isinstance(manual, str) and manual:
        return manual.split("\n")[0].strip()
    return ""


def build_driver_status_display(
    error: Any,
    post_install_message: str | None,
    strategy_resolver: InstallStrategyResolver,
) -> DriverStatusDisplay:
    if error:
        if getattr(error, "import_error", None):
            detail = str(error.import_error).splitlines()[0].strip()
            detail_hint = escape(detail) if detail else "Import failed."
            message = (
                f"[yellow]⚠ Driver failed to load:[/] {error.package_name}\n"
                f"[dim]{detail_hint} Press ^i for details.[/]"
            )
            subtitle = "[bold]Help ^i[/]  Cancel <esc>"
            return DriverStatusDisplay(message=message, subtitle=subtitle)

        strategy = strategy_resolver.detect(
            extra_name=error.extra_name,
            package_name=error.package_name,
        )
        if strategy.can_auto_install:
            install_cmd = _format_install_hint(strategy)
            message = (
                f"[yellow]⚠ Missing driver:[/] {error.package_name}\n"
                f"[dim]Install with:[/] {escape(install_cmd)}"
            )
            subtitle = "[bold]Install ^i[/]  Cancel <esc>"
            return DriverStatusDisplay(message=message, subtitle=subtitle)

        reason = strategy.reason_unavailable or "Auto-install not available"
        message = (
            f"[yellow]⚠ Missing driver:[/] {error.package_name}\n"
            f"[dim]{escape(reason)} Press ^i for install instructions.[/]"
        )
        subtitle = "[bold]Help ^i[/]  Cancel <esc>"
        return DriverStatusDisplay(message=message, subtitle=subtitle)

    if post_install_message:
        return DriverStatusDisplay(
            message=f"✓ {post_install_message}",
            subtitle="[bold]Test ^t[/]  Save ^s  Cancel <esc>",
            success=True,
        )

    return DriverStatusDisplay(message="", subtitle="[bold]Test ^t[/]  Save ^s  Cancel <esc>")
