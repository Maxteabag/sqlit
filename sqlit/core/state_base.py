"""Shared state machine building blocks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto

from sqlit.core.input_context import InputContext


def resolve_display_key(action_name: str) -> str | None:
    from sqlit.core.keymap import format_key, get_keymap

    key = get_keymap().action(action_name)
    return format_key(key) if key else None


def resolve_help_key(action_name: str) -> str | None:
    from sqlit.core.keymap import format_key, get_keymap

    keys = get_keymap().keys_for_action(action_name, include_secondary=True)
    if not keys:
        return None
    return "/".join(format_key(key) for key in keys)


class ActionResult(Enum):
    """Result of checking an action in a state."""

    ALLOWED = auto()  # Action is allowed
    FORBIDDEN = auto()  # Action is explicitly forbidden
    UNHANDLED = auto()  # State doesn't handle this action (delegate to parent)


@dataclass
class DisplayBinding:
    """A binding to display in the footer."""

    key: str  # Display key (e.g., "enter", "y", "<space>")
    label: str  # Human-readable label (e.g., "Connect", "Yes")
    action: str  # Action name for reference


@dataclass
class HelpEntry:
    """An entry for the help text."""

    key: str  # Display key (e.g., "enter", "s")
    description: str  # Help description (e.g., "Select TOP 100")
    category: str  # Category name (e.g., "Explorer")


@dataclass
class ActionSpec:
    """Specification for an action."""

    guard: Callable[[InputContext], bool] | None = None
    display_key: str | None = None
    display_label: str | None = None
    help_key: str | None = None
    help_description: str | None = None

    def is_allowed(self, app: InputContext) -> bool:
        if self.guard is None:
            return True
        return self.guard(app)

    def get_display_binding(self, action_name: str) -> DisplayBinding | None:
        if not self.display_label:
            return None
        key = self.display_key or resolve_display_key(action_name)
        if not key:
            return None
        return DisplayBinding(
            key=key,
            label=self.display_label,
            action=action_name,
        )

    def get_help_entry(self, action_name: str, category: str) -> HelpEntry | None:
        """Get help entry if help info is defined."""
        if not self.help_description:
            return None
        key = self.help_key or resolve_help_key(action_name)
        if not key:
            return None
        return HelpEntry(
            key=key,
            description=self.help_description,
            category=category,
        )


class State(ABC):
    """Base class for hierarchical states."""

    help_category: str | None = None

    def __init__(self, parent: State | None = None):
        self.parent = parent
        self._actions: dict[str, ActionSpec] = {}
        self._forbidden: set[str] = set()
        self._display_order: list[str] = []
        self._right_bindings: list[str] = []
        self._setup_actions()

    @abstractmethod
    def _setup_actions(self) -> None:
        """Override to define actions handled by this state."""
        raise NotImplementedError

    def allows(
        self,
        action_name: str,
        guard: Callable[[InputContext], bool] | None = None,
        *,
        key: str | None = None,
        label: str | None = None,
        right: bool = False,
        help: str | None = None,
        help_key: str | None = None,
    ) -> None:
        """Register an action as allowed in this state."""
        self._actions[action_name] = ActionSpec(
            guard=guard,
            display_key=key,
            display_label=label,
            help_key=help_key or key,
            help_description=help,
        )
        if key and label:
            if right:
                self._right_bindings.append(action_name)
            else:
                self._display_order.append(action_name)

    def get_help_entries(self) -> list[HelpEntry]:
        """Get all help entries from this state."""
        entries = []
        if self.help_category:
            for action_name, spec in self._actions.items():
                entry = spec.get_help_entry(action_name, self.help_category)
                if entry:
                    entries.append(entry)
        return entries

    def forbids(self, *action_names: str) -> None:
        """Explicitly forbid actions (blocks parent allowance)."""
        self._forbidden.update(action_names)

    def check_action(self, app: InputContext, action_name: str) -> ActionResult:
        """Check if action is allowed in this state or ancestors."""
        if action_name in self._forbidden:
            return ActionResult.FORBIDDEN

        if action_name in self._actions:
            spec = self._actions[action_name]
            if spec.is_allowed(app):
                return ActionResult.ALLOWED
            return ActionResult.FORBIDDEN

        if self.parent:
            return self.parent.check_action(app, action_name)

        return ActionResult.UNHANDLED

    def get_display_bindings(self, app: InputContext) -> tuple[list[DisplayBinding], list[DisplayBinding]]:
        """Get bindings to display in footer (left, right)."""
        left: list[DisplayBinding] = []
        right: list[DisplayBinding] = []
        seen: set[str] = set()

        for action_name in self._display_order:
            if action_name in seen:
                continue
            spec = self._actions.get(action_name)
            if spec and spec.is_allowed(app):
                binding = spec.get_display_binding(action_name)
                if binding:
                    left.append(binding)
                    seen.add(action_name)

        for action_name in self._right_bindings:
            if action_name in seen:
                continue
            spec = self._actions.get(action_name)
            if spec and spec.is_allowed(app):
                binding = spec.get_display_binding(action_name)
                if binding:
                    right.append(binding)
                    seen.add(action_name)

        if self.parent:
            parent_left, parent_right = self.parent.get_display_bindings(app)
            for binding in parent_left:
                if binding.action not in seen:
                    left.append(binding)
                    seen.add(binding.action)
            for binding in parent_right:
                if binding.action not in seen:
                    right.append(binding)
                    seen.add(binding.action)

        return left, right

    @abstractmethod
    def is_active(self, app: InputContext) -> bool:
        """Return True if this state is currently active."""
        raise NotImplementedError


class BlockingState(State):
    """State that blocks all actions except those explicitly allowed."""

    def check_action(self, app: InputContext, action_name: str) -> ActionResult:
        if action_name in self._forbidden:
            return ActionResult.FORBIDDEN

        if action_name in self._actions:
            spec = self._actions[action_name]
            if spec.is_allowed(app):
                return ActionResult.ALLOWED
            return ActionResult.FORBIDDEN

        return ActionResult.FORBIDDEN
