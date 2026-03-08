"""Shared helpers for cloud provider UI adapters."""

from __future__ import annotations


def format_saved_label(label: str, saved: bool) -> str:
    if saved:
        return f"[dim]{label} ✓[/]"
    return label
