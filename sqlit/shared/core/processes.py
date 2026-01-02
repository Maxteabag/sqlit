"""Process runner protocols and default implementations."""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@runtime_checkable
class SyncProcess(Protocol):
    """Protocol for synchronous process handles."""

    @property
    def returncode(self) -> int | None:
        ...

    def communicate(self, input: str | None = None, timeout: float | None = None) -> tuple[str, str]:
        ...

    def terminate(self) -> None:
        ...

    def kill(self) -> None:
        ...

    def wait(self, timeout: float | None = None) -> int:
        ...


@runtime_checkable
class SyncProcessRunner(Protocol):
    """Protocol for spawning synchronous processes."""

    def spawn(self, command: list[str], *, cwd: str | None = None) -> SyncProcess:
        ...


@dataclass
class SubprocessRunner(SyncProcessRunner):
    """Default runner using subprocess.Popen."""

    def spawn(self, command: list[str], *, cwd: str | None = None) -> SyncProcess:
        return subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
        )


@dataclass
class FixedResultSyncProcess:
    returncode: int
    stdout: str = ""
    stderr: str = ""

    def communicate(self, input: str | None = None, timeout: float | None = None) -> tuple[str, str]:
        return self.stdout, self.stderr

    def terminate(self) -> None:
        return None

    def kill(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode


@dataclass
class FixedResultSyncRunner(SyncProcessRunner):
    """Runner that returns a fixed exit code/output."""

    returncode: int
    stdout: str = ""
    stderr: str = ""

    def spawn(self, command: list[str], *, cwd: str | None = None) -> SyncProcess:
        return FixedResultSyncProcess(returncode=self.returncode, stdout=self.stdout, stderr=self.stderr)


@runtime_checkable
class AsyncProcess(Protocol):
    """Protocol for asynchronous process handles."""

    stdout: asyncio.StreamReader | None

    @property
    def returncode(self) -> int | None:
        ...

    async def wait(self) -> int:
        ...

    def terminate(self) -> None:
        ...


@runtime_checkable
class AsyncProcessRunner(Protocol):
    """Protocol for spawning asynchronous processes."""

    async def spawn(self, command: str) -> AsyncProcess:
        ...


@dataclass
class AsyncSubprocessRunner(AsyncProcessRunner):
    """Default async runner using asyncio subprocess shell."""

    async def spawn(self, command: str) -> AsyncProcess:
        return await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )


@dataclass
class FixedResultAsyncProcess:
    returncode: int
    stdout: asyncio.StreamReader | None

    async def wait(self) -> int:
        return self.returncode

    def terminate(self) -> None:
        return None


@dataclass
class FixedResultAsyncRunner(AsyncProcessRunner):
    """Async runner that returns a fixed exit code/output."""

    returncode: int
    lines: list[str] = field(default_factory=list)

    async def spawn(self, command: str) -> AsyncProcess:
        reader = asyncio.StreamReader()
        for line in self.lines:
            reader.feed_data((line + "\n").encode("utf-8"))
        reader.feed_eof()
        return FixedResultAsyncProcess(returncode=self.returncode, stdout=reader)
