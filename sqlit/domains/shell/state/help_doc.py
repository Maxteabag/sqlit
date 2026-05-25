"""Structured help document model.

Help content is generated as an ordered list of `HelpSection`s. Each section
has a stable `id` so the UI can scroll/reorder by current context, and each
binding item carries its raw key + description so the view can filter by
substring without re-parsing rendered markup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class HelpItem:
    """A single line inside a help section."""

    kind: Literal["binding", "subsection"]
    key: str = ""
    description: str = ""
    title: str = ""

    def matches(self, query: str) -> bool:
        """Substring match against key + description (case-insensitive)."""
        if not query:
            return True
        q = query.lower()
        if self.kind == "subsection":
            return q in self.title.lower()
        return q in self.key.lower() or q in self.description.lower()


@dataclass
class HelpSection:
    """A titled group of help items."""

    id: str
    title: str
    items: list[HelpItem] = field(default_factory=list)

    def binding(self, key: str, description: str) -> HelpSection:
        self.items.append(HelpItem(kind="binding", key=key, description=description))
        return self

    def subsection(self, title: str) -> HelpSection:
        self.items.append(HelpItem(kind="subsection", title=title))
        return self


def render_section(section: HelpSection, query: str = "") -> tuple[str, int]:
    """Render a section to Rich markup. Returns (markup, matched_item_count).

    When `query` is non-empty, items not matching are skipped. A subsection
    header is kept only if at least one following binding (up to the next
    subsection) matches.
    """
    divider = "-" * 62
    lines: list[str] = [f"[bold $primary]{section.title}[/]", f"[dim]{divider}[/]"]
    matched = 0

    items = section.items
    if query:
        kept: list[HelpItem] = []
        i = 0
        while i < len(items):
            item = items[i]
            if item.kind == "subsection":
                j = i + 1
                group_match = False
                group: list[HelpItem] = []
                while j < len(items) and items[j].kind != "subsection":
                    if items[j].matches(query):
                        group_match = True
                        group.append(items[j])
                    j += 1
                if group_match:
                    kept.append(item)
                    kept.extend(group)
                i = j
            else:
                if item.matches(query):
                    kept.append(item)
                i += 1
        items = kept

    for item in items:
        if item.kind == "subsection":
            lines.append(f"  [bold $text-muted]{item.title}[/]")
        else:
            lines.append(
                f"    [bold $warning]{item.key:<14}[/] [dim]-[/] {item.description}"
            )
            matched += 1

    return "\n".join(lines), matched
