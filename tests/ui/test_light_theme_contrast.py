"""Contrast regressions for command mode across Sqlit's light themes."""

from __future__ import annotations

import pytest

from sqlit.domains.shell.app.main import SSMSTUI

from .mocks import MockConnectionStore, MockSettingsStore, build_test_services

LIGHT_THEMES = [
    "sqlit-light",
    "textual-light",
    "solarized-light",
    "catppuccin-latte",
    "rose-pine-dawn",
    "gruvbox-light",
]


def _relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]

    def linearize(channel: float) -> float:
        if channel <= 0.04045:
            return channel / 12.92
        return ((channel + 0.055) / 1.055) ** 2.4

    red, green, blue = (linearize(channel) for channel in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize("theme_name", LIGHT_THEMES)
@pytest.mark.asyncio
async def test_command_mode_uses_contrasting_theme_primary(theme_name: str) -> None:
    services = build_test_services(
        connection_store=MockConnectionStore(),
        settings_store=MockSettingsStore({"theme": theme_name}),
    )
    app = SSMSTUI(services=services)

    async with app.run_test() as pilot:
        await pilot.pause()
        app._command_mode = True
        app._command_buffer = "theme"
        app._update_status_bar()
        await pilot.pause()

        rendered = app.status_bar.render()
        assert rendered.plain == ":theme"
        assert rendered.spans[0].style == f"bold {app.current_theme.primary}"
        assert _contrast_ratio(app.current_theme.primary, app.current_theme.surface) >= 3
