"""Dialog widgets for sqlit."""

from __future__ import annotations

from typing import Any

from textual.containers import Container


class Dialog(Container):
    """A styled modal dialog container with optional border title/subtitle.

    The shortcuts parameter accepts a list of (action, key) tuples that will be
    formatted consistently as "action: [bold]key[/]" in the subtitle.
    """

    DEFAULT_CSS = """
    Dialog {
        border: round $primary;
        background: $surface;
        color: $primary;
        padding: 1;
        height: auto;
        max-height: 85%;
        overflow-x: hidden;
        overflow-y: auto;
        scrollbar-visibility: hidden;

        border-title-align: left;
        border-title-color: $primary;
        border-title-background: $surface;
        border-title-style: bold;

        border-subtitle-align: right;
        border-subtitle-color: $primary;
        border-subtitle-background: $surface;
        border-subtitle-style: none;
    }
    """

    def __init__(
        self,
        title: str | None = None,
        shortcuts: list[tuple[str, str]] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the dialog.

        Args:
            title: The dialog title (shown in border title).
            shortcuts: List of (action, key) tuples for the subtitle.
                       Example: [("Save", "^S"), ("Cancel", "<esc>")]
        """
        super().__init__(**kwargs)
        if title is not None:
            self.border_title = title
        if shortcuts:
            # Use a visible separator. Border subtitles can collapse regular spaces,
            # so we use non-breaking spaces to preserve padding around the separator.
            def format_key(key: str) -> str:
                # Wrap key in <> if not already wrapped
                if key.startswith("<") and key.endswith(">"):
                    return key
                return f"<{key}>"

            subtitle = "\u00a0·\u00a0".join(
                f"{action}: [bold]{format_key(key)}[/]" for action, key in shortcuts
            )
            self.border_subtitle = subtitle
