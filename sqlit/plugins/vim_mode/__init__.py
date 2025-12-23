"""Vim mode plugin for sqlit.

This plugin provides vim-like keybindings for the query editor.
Toggle with <space>v. Disabled by default.
"""

from ..  import register_plugin
from .plugin import VimModePlugin

# Register the plugin
register_plugin(VimModePlugin)

__all__ = ["VimModePlugin"]
