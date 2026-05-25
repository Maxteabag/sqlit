"""Help screen showing keyboard shortcuts."""

from __future__ import annotations

from rich.markup import escape as escape_markup
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Static

from sqlit.domains.shell.state.help_doc import HelpSection, render_section
from sqlit.shared.ui.widgets import Dialog


class HelpScreen(ModalScreen):
    """Modal screen showing keyboard shortcuts and navigation tips.

    The section matching the active UI context (when help was opened) is
    rendered first. `/` enters a filter-by-substring mode; Esc backs out of
    search, then clears any applied filter, then closes the screen.
    """

    BINDINGS = [
        Binding("escape", "escape", "Close", show=False),
        Binding("enter,q", "dismiss_modal", "Close", show=False),
        Binding("j", "scroll_down", "Scroll down", show=False),
        Binding("k", "scroll_up", "Scroll up", show=False),
        Binding("g", "scroll_home", "Scroll to top", show=False),
        Binding("G", "scroll_end", "Scroll to bottom", show=False),
        Binding("slash", "start_search", "Search", show=False),
    ]

    CSS = """
    HelpScreen {
        align: center middle;
        background: transparent;
    }

    #help-dialog {
        width: 82;
        max-width: 90%;
        max-height: 85%;
        background: $surface;
        border: round $primary;
        padding: 1 2;
        border-title-background: $surface;
        border-subtitle-background: $surface;
        border-title-color: $primary;
        border-subtitle-color: $primary;
    }

    #help-scroll {
        height: auto;
        max-height: 100%;
        background: transparent;
        border: none;
        scrollbar-gutter: stable;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        sections: list[HelpSection],
        active_section_id: str | None = None,
    ) -> None:
        super().__init__()
        self._sections = sections
        self._active_section_id = active_section_id
        self._ordered = self._reorder(sections, active_section_id)
        self._search: str = ""
        self._searching: bool = False

    @staticmethod
    def _reorder(
        sections: list[HelpSection], active_id: str | None
    ) -> list[HelpSection]:
        if not active_id:
            return list(sections)
        front = [s for s in sections if s.id == active_id]
        rest = [s for s in sections if s.id != active_id]
        return front + rest

    def compose(self) -> ComposeResult:
        with Dialog(id="help-dialog", title="Keyboard Shortcuts"):
            with VerticalScroll(id="help-scroll"):
                yield Static(self._build_markup(), id="help-content", markup=True)

    def on_mount(self) -> None:
        self._refresh_subtitle()

    def _build_markup(self) -> str:
        parts: list[str] = []
        total_matches = 0
        rendered_sections = 0
        for section in self._ordered:
            markup, matched = render_section(section, self._search)
            if self._search and matched == 0:
                continue
            parts.append(markup)
            total_matches += matched
            rendered_sections += 1

        if self._search and rendered_sections == 0:
            safe = escape_markup(self._search)
            parts.append(f'[dim]No bindings match "{safe}"[/]')

        if self._searching or self._search:
            safe = escape_markup(self._search) if self._search else ""
            cursor = "[reverse] [/]" if self._searching else ""
            suffix = "es" if total_matches != 1 else ""
            header = (
                f"[bold $primary]/[/] {safe}{cursor}"
                f"  [dim]({total_matches} match{suffix})[/]"
            )
            parts.insert(0, header + "\n")

        return "\n\n".join(parts) if parts else "[dim]No help available[/]"

    def _refresh(self) -> None:
        self.query_one("#help-content", Static).update(self._build_markup())
        self._refresh_subtitle()
        scroll = self.query_one("#help-scroll", VerticalScroll)
        scroll.scroll_home(animate=False)

    def _refresh_subtitle(self) -> None:
        dialog = self.query_one("#help-dialog", Dialog)
        if self._searching:
            dialog.border_subtitle = "Type to filter · [bold]<esc>[/] cancel"
        elif self._search:
            dialog.border_subtitle = "Filtered · [bold]/[/] edit · [bold]<esc>[/] clear"
        else:
            dialog.border_subtitle = "[bold]/[/] search · [bold]<esc>[/] close"

    def action_dismiss_modal(self) -> None:
        if self._searching:
            self._searching = False
            self._refresh()
            return
        self.dismiss(None)

    def action_escape(self) -> None:
        if self._searching:
            self._searching = False
            self._refresh()
            return
        if self._search:
            self._search = ""
            self._refresh()
            return
        self.dismiss(None)

    def action_start_search(self) -> None:
        self._searching = True
        self._refresh()

    def action_scroll_down(self) -> None:
        self.query_one("#help-scroll", VerticalScroll).scroll_down()

    def action_scroll_up(self) -> None:
        self.query_one("#help-scroll", VerticalScroll).scroll_up()

    def action_scroll_home(self) -> None:
        self.query_one("#help-scroll", VerticalScroll).scroll_home()

    def action_scroll_end(self) -> None:
        self.query_one("#help-scroll", VerticalScroll).scroll_end()

    async def on_key(self, event: Key) -> None:
        if not self._searching:
            return

        if event.key == "escape":
            event.stop()
            event.prevent_default()
            self._searching = False
            self._refresh()
            return

        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self._searching = False
            self._refresh()
            return

        if event.key == "backspace":
            event.stop()
            event.prevent_default()
            if self._search:
                self._search = self._search[:-1]
                self._refresh()
            return

        if event.is_printable and event.character:
            event.stop()
            event.prevent_default()
            self._search += event.character
            self._refresh()
