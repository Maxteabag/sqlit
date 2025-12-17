"""Utility functions for sqlit."""

from __future__ import annotations


def fuzzy_match(pattern: str, text: str) -> tuple[bool, list[int]]:
    """Check if pattern fuzzy matches text and return matched indices.

    Args:
        pattern: The search pattern (e.g., "usrtbl" to match "users_table")
        text: The text to search in

    Returns:
        Tuple of (matches, indices) where indices are positions in text that matched.
    """
    if not pattern:
        return True, []

    pattern = pattern.lower()
    text_lower = text.lower()

    pattern_idx = 0
    indices = []

    for i, char in enumerate(text_lower):
        if pattern_idx < len(pattern) and char == pattern[pattern_idx]:
            indices.append(i)
            pattern_idx += 1

    return pattern_idx == len(pattern), indices


def highlight_matches(text: str, indices: list[int], style: str = "bold yellow") -> str:
    """Highlight matched characters in text using Rich markup.

    Args:
        text: The original text
        indices: List of character indices to highlight
        style: Rich style string for highlighting (default: "bold yellow")

    Returns:
        Text with Rich markup highlighting the matched characters.
    """
    if not indices:
        return text

    result = []
    idx_set = set(indices)

    for i, char in enumerate(text):
        if i in idx_set:
            result.append(f"[{style}]{char}[/]")
        else:
            result.append(char)

    return "".join(result)


def format_duration_ms(ms: float, *, always_seconds: bool = False) -> str:
    """Format milliseconds into a human-readable duration string.

    Args:
        ms: Duration in milliseconds
        always_seconds: If True, always format as seconds (e.g., "0.00s")

    Returns:
        Formatted duration string
    """
    if always_seconds:
        return f"{ms / 1000:.2f}s"
    if ms >= 1000:
        return f"{ms / 1000:.2f}s"
    elif ms >= 1:
        return f"{ms:.0f}ms"
    else:
        return f"{ms:.2f}ms"
