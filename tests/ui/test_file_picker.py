"""UI tests for the shared file picker."""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.app import App
from textual.widgets import Static

from sqlit.shared.ui.screens.file_picker import FilePickerMode, FilePickerScreen


class _FilePickerApp(App[None]):
    def __init__(self, start_directory: Path) -> None:
        super().__init__()
        self.start_directory = start_directory

    async def on_mount(self) -> None:
        await self.push_screen(
            FilePickerScreen(
                mode=FilePickerMode.SAVE,
                start_directory=self.start_directory,
            )
        )


@pytest.mark.asyncio
async def test_file_picker_rows_are_not_text_selectable_and_mouse_navigation_works(
    tmp_path: Path,
) -> None:
    child = tmp_path / "child"
    child.mkdir()
    app = _FilePickerApp(tmp_path)

    async with app.run_test(size=(100, 35)) as pilot:
        screen = app.screen
        labels = list(screen.query(Static))

        assert labels
        assert all(not label.allow_select for label in labels)

        child_label = next(label for label in labels if "child" in str(label.render()))
        await pilot.click(child_label)
        await pilot.pause()

        assert screen._current_dir == child
