"""Core protocol definitions for Textual App interactions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, overload

if TYPE_CHECKING:
    from textual.screen import Screen
    from textual.timer import Timer
    from textual.widget import Widget
    from textual.worker import Worker

QueryType = TypeVar("QueryType", bound="Widget")


class TextualAppProtocol(Protocol):
    """Base protocol for Textual App methods and properties."""

    def notify(
        self,
        message: str,
        *,
        title: str = "",
        severity: str = "information",
        timeout: float | None = None,
        markup: bool = True,
    ) -> None:
        ...

    def push_screen(
        self,
        screen: Screen[Any] | str,
        callback: Callable[[Any], None] | Callable[[Any], Awaitable[None]] | None = None,
        wait_for_dismiss: bool = False,
    ) -> Any:
        ...

    def pop_screen(self) -> Any:
        ...

    def run_worker(
        self,
        work: Any,
        name: str | None = "",
        group: str = "default",
        description: str = "",
        exit_on_error: bool = True,
        start: bool = True,
        exclusive: bool = False,
        thread: bool = False,
    ) -> Worker[Any]:
        ...

    def call_later(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> bool:
        ...

    def call_from_thread(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        ...

    def call_after_refresh(self, callback: Callable[[], Any]) -> None:
        ...

    def set_timer(
        self,
        delay: float,
        callback: Callable[[], None] | None = None,
        *,
        name: str | None = None,
        pause: bool = False,
    ) -> Timer:
        ...

    def set_interval(
        self,
        interval: float,
        callback: Callable[[], None] | None = None,
        *,
        name: str | None = None,
        repeat: int = 0,
        pause: bool = False,
    ) -> Timer:
        ...

    @overload
    def query_one(self, selector: str) -> Widget: ...

    @overload
    def query_one(self, selector: type[QueryType]) -> QueryType: ...

    @overload
    def query_one(self, selector: str, expect_type: type[QueryType]) -> QueryType: ...

    def query_one(self, selector: Any, expect_type: Any = None) -> Any:
        ...

    def copy_to_clipboard(self, text: str) -> None:
        ...

    def exit(self, result: Any = None, return_code: int = 0, message: Any | None = None) -> None:
        ...

    @property
    def screen(self) -> Screen[Any]:
        ...

    @property
    def screen_stack(self) -> list[Screen[Any]]:
        ...

    @property
    def focused(self) -> Any:
        ...

    @property
    def app(self) -> Any:
        ...

    @property
    def size(self) -> Any:
        ...

    @property
    def theme(self) -> str:
        ...

    @theme.setter
    def theme(self, value: str) -> None:
        ...

    def get_custom_theme_names(self) -> set[str]:
        ...

    def add_custom_theme(self, theme_name: str) -> str:
        ...

    def get_custom_theme_path(self, theme_name: str) -> Any:
        ...

    def open_custom_theme_in_editor(self, theme_name: str) -> None:
        ...
