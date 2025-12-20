"""Omarchy theme integration for sqlit.

Provides automatic theme synchronization with Omarchy's theme system.
Only activates when Omarchy is detected on the system.

Theme matching strategy:
1. Get the current Omarchy theme name from the symlink
2. Try to match it to a built-in Textual theme
3. If no match, fall back to the default "rose-pine" theme
"""

from __future__ import annotations

from pathlib import Path

# Omarchy paths
OMARCHY_CONFIG_DIR = Path.home() / ".config" / "omarchy"
OMARCHY_CURRENT_THEME = OMARCHY_CONFIG_DIR / "current" / "theme"

# Default theme when no Omarchy match is found
DEFAULT_THEME = "rose-pine"

# Mapping from Omarchy theme names to Textual theme names
# Only needed when names don't match exactly
THEME_ALIASES: dict[str, str] = {
    # Omarchy "catppuccin" is the dark variant (mocha)
    "catppuccin": "catppuccin-mocha",
    # Flexoki light variant
    "flexoki-light": "flexoki",
}


def is_omarchy_installed() -> bool:
    """Check if Omarchy is installed by looking for the current theme symlink."""
    return OMARCHY_CURRENT_THEME.exists()


def get_current_theme_path() -> Path | None:
    """Get the path to the current Omarchy theme directory.

    Returns:
        Path to the current theme directory, or None if not available.
    """
    if not OMARCHY_CURRENT_THEME.exists():
        return None

    try:
        return OMARCHY_CURRENT_THEME.resolve()
    except OSError:
        return None


def get_current_theme_name() -> str | None:
    """Get the name of the current Omarchy theme.

    Returns:
        Theme name (directory name), or None if not available.
    """
    theme_path = get_current_theme_path()
    if theme_path is None:
        return None
    return theme_path.name


def get_matching_textual_theme(available_themes: set[str]) -> str:
    """Get a Textual theme that matches the current Omarchy theme.

    Args:
        available_themes: Set of available Textual theme names.

    Returns:
        The matching Textual theme name, or DEFAULT_THEME if no match.
    """
    omarchy_theme = get_current_theme_name()
    if omarchy_theme is None:
        return DEFAULT_THEME

    # Normalize to lowercase for matching
    omarchy_lower = omarchy_theme.lower()

    # Check for exact match first
    if omarchy_lower in available_themes:
        return omarchy_lower

    # Check aliases
    if omarchy_lower in THEME_ALIASES:
        alias = THEME_ALIASES[omarchy_lower]
        if alias in available_themes:
            return alias

    # No match found
    return DEFAULT_THEME
