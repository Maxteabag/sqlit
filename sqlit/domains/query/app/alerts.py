"""Query alert classification and alert mode helpers."""

from __future__ import annotations

import re
from enum import IntEnum

from sqlit.domains.query.app.multi_statement import split_statements


class AlertMode(IntEnum):
    """Alert mode thresholds (user-configured)."""

    OFF = 0
    DELETE = 1
    WRITE = 2


class AlertSeverity(IntEnum):
    """Severity classification for a query."""

    NONE = 0
    WRITE = 1
    DELETE = 2


_DELETE_KEYWORDS = ("DELETE",)
_WRITE_KEYWORDS = (
    "CREATE",
    "ALTER",
    "DROP",
    "TRUNCATE",
    "RENAME",
    "INSERT",
    "UPDATE",
    "MERGE",
    "REPLACE",
    "UPSERT",
    "DELETE",
)

_DELETE_RE = re.compile(r"\b(?:%s)\b" % "|".join(_DELETE_KEYWORDS), re.IGNORECASE)
_WRITE_RE = re.compile(r"\b(?:%s)\b" % "|".join(_WRITE_KEYWORDS), re.IGNORECASE)

_SINGLE_QUOTE_RE = re.compile(r"'[^']*'")
_DOUBLE_QUOTE_RE = re.compile(r'"[^"]*"')
_BACKTICK_RE = re.compile(r"`[^`]*`")
_BRACKET_RE = re.compile(r"\[[^\]]*]")
_LINE_COMMENT_RE = re.compile(r"--[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def parse_alert_mode(value: str | int | None) -> AlertMode | None:
    """Parse a user-provided alert mode value."""
    if value is None:
        return None
    if isinstance(value, int):
        return _coerce_alert_mode(value)
    raw = str(value).strip().lower()
    if not raw:
        return None
    if raw in {"0", "off", "none", "disable", "disabled"}:
        return AlertMode.OFF
    if raw in {"1", "delete", "destructive", "danger"}:
        return AlertMode.DELETE
    if raw in {"2", "write", "writes", "edit", "update"}:
        return AlertMode.WRITE
    return None


def format_alert_mode(mode: AlertMode) -> str:
    """Human-readable alert mode."""
    if mode == AlertMode.DELETE:
        return "delete"
    if mode == AlertMode.WRITE:
        return "write"
    return "off"


def should_confirm(mode: AlertMode, severity: AlertSeverity) -> bool:
    """Return True if the given severity should prompt confirmation."""
    if mode == AlertMode.DELETE:
        return severity == AlertSeverity.DELETE
    if mode == AlertMode.WRITE:
        return severity in {AlertSeverity.WRITE, AlertSeverity.DELETE}
    return False


def classify_query_alert(sql: str) -> AlertSeverity:
    """Classify a SQL query for alerting."""
    if not sql:
        return AlertSeverity.NONE
    highest = AlertSeverity.NONE
    for statement in split_statements(sql):
        severity = _classify_statement(statement)
        if severity == AlertSeverity.DELETE:
            return severity
        if severity.value > highest.value:
            highest = severity
    return highest


def _classify_statement(statement: str) -> AlertSeverity:
    cleaned = _strip_comments_and_literals(statement)
    if not cleaned:
        return AlertSeverity.NONE
    if _DELETE_RE.search(cleaned):
        return AlertSeverity.DELETE
    if _WRITE_RE.search(cleaned):
        return AlertSeverity.WRITE
    return AlertSeverity.NONE


def _strip_comments_and_literals(sql: str) -> str:
    """Remove comments and quoted literals/identifiers for keyword scanning."""
    cleaned = _LINE_COMMENT_RE.sub("", sql)
    cleaned = _BLOCK_COMMENT_RE.sub("", cleaned)
    cleaned = _SINGLE_QUOTE_RE.sub("''", cleaned)
    cleaned = _DOUBLE_QUOTE_RE.sub('""', cleaned)
    cleaned = _BACKTICK_RE.sub("``", cleaned)
    cleaned = _BRACKET_RE.sub("[]", cleaned)
    return cleaned


def _coerce_alert_mode(value: int) -> AlertMode | None:
    try:
        mode = AlertMode(int(value))
    except (TypeError, ValueError):
        return None
    if mode in {AlertMode.OFF, AlertMode.DELETE, AlertMode.WRITE}:
        return mode
    return None
