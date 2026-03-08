"""File save dialog - re-exports from shared module for backwards compatibility."""

from sqlit.shared.ui.screens.file_picker import FilePickerMode, FilePickerScreen

# Backwards compatible alias
SaveFileScreen = FilePickerScreen

__all__ = ["FilePickerMode", "FilePickerScreen", "SaveFileScreen"]
