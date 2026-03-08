"""State classes for the shell app."""

from sqlit.domains.shell.state.leader_pending import LeaderPendingState
from sqlit.domains.shell.state.machine import UIStateMachine
from sqlit.domains.shell.state.main_screen import MainScreenState
from sqlit.domains.shell.state.modal_active import ModalActiveState
from sqlit.domains.shell.state.query_executing import QueryExecutingState
from sqlit.domains.shell.state.root import RootState

__all__ = [
    "LeaderPendingState",
    "MainScreenState",
    "ModalActiveState",
    "QueryExecutingState",
    "RootState",
    "UIStateMachine",
]
