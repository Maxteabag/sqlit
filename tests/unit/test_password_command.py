"""Tests for password command utility."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from sqlit.domains.connections.domain.password_command import (
    PasswordCommandError,
    run_password_command,
)


class TestRunPasswordCommand:
    def test_returns_stripped_stdout(self) -> None:
        mock_result = subprocess.CompletedProcess(
            args="cmd", returncode=0, stdout="  secret\n", stderr=""
        )
        with patch("subprocess.run", return_value=mock_result):
            assert run_password_command("cmd") == "secret"

    def test_raises_on_nonzero_exit(self) -> None:
        mock_result = subprocess.CompletedProcess(
            args="cmd", returncode=1, stdout="", stderr="access denied"
        )
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(PasswordCommandError, match="exit 1.*access denied"):
                run_password_command("cmd")

    def test_raises_on_timeout(self) -> None:
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired("cmd", 30),
        ):
            with pytest.raises(PasswordCommandError, match="timed out"):
                run_password_command("cmd")

    def test_raises_on_file_not_found(self) -> None:
        with patch(
            "subprocess.run",
            side_effect=FileNotFoundError("No such file"),
        ):
            with pytest.raises(PasswordCommandError, match="Command not found"):
                run_password_command("cmd")

    def test_real_echo_command(self) -> None:
        assert run_password_command("echo secret") == "secret"

    def test_real_echo_strips_whitespace(self) -> None:
        assert run_password_command("echo '  hello  '") == "hello"
