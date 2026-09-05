"""Tests for the stdin-secret reader used by --password-stdin / --url-stdin."""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest

from sqlit.domains.connections.domain.stdin_secret import (
    StdinSecretError,
    read_secret_from_stdin,
)


class _FakeStream(io.StringIO):
    def __init__(self, contents: str, *, isatty: bool = False) -> None:
        super().__init__(contents)
        self._isatty = isatty

    def isatty(self) -> bool:  # type: ignore[override]
        return self._isatty


class TestReadSecretFromStdin:
    def test_strips_trailing_newline(self) -> None:
        assert read_secret_from_stdin(stream=_FakeStream("secret\n")) == "secret"

    def test_strips_crlf(self) -> None:
        assert read_secret_from_stdin(stream=_FakeStream("secret\r\n")) == "secret"

    def test_preserves_internal_spaces(self) -> None:
        assert read_secret_from_stdin(stream=_FakeStream("a b c\n")) == "a b c"

    def test_no_trailing_newline_is_returned_verbatim(self) -> None:
        assert read_secret_from_stdin(stream=_FakeStream("naked")) == "naked"

    def test_only_reads_first_line(self) -> None:
        stream = _FakeStream("first\nsecond\n")
        assert read_secret_from_stdin(stream=stream) == "first"

    def test_refuses_tty(self) -> None:
        with pytest.raises(StdinSecretError, match="TTY"):
            read_secret_from_stdin(stream=_FakeStream("ignored\n", isatty=True))

    def test_refuses_empty_stream(self) -> None:
        with pytest.raises(StdinSecretError, match="EOF"):
            read_secret_from_stdin(stream=_FakeStream(""))

    def test_label_appears_in_tty_error(self) -> None:
        with pytest.raises(StdinSecretError, match="url"):
            read_secret_from_stdin(label="url", stream=_FakeStream("x", isatty=True))

    def test_label_appears_in_eof_error(self) -> None:
        with pytest.raises(StdinSecretError, match="ssh-password"):
            read_secret_from_stdin(label="ssh-password", stream=_FakeStream(""))

    def test_defaults_to_sys_stdin(self) -> None:
        with patch("sqlit.domains.connections.domain.stdin_secret.sys") as mock_sys:
            mock_sys.stdin = _FakeStream("from-real-stdin\n")
            assert read_secret_from_stdin() == "from-real-stdin"
