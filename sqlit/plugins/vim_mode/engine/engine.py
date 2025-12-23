"""Vim emulation engine.

The VimEngine is the main controller that:
- Handles key events from the TextArea
- Manages vim state (mode, pending operator, etc.)
- Dispatches to motions, operators, and text objects
- Coordinates with the TextArea for cursor movement and text changes
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Any

from .state import VimMode, VimState, TextObjectType
from .document import DocumentWrapper
from .keymap import get_vim_keymap, BindingType
from .motions import get_motion_handler, motion_find_char, MotionResult
from .operators import get_operator_handler
from .text_objects import get_text_object_handler
from .command import VimCommandHandler, CommandResult, CommandAction

if TYPE_CHECKING:
    from textual.widgets import TextArea


@dataclass
class KeyResult:
    """Result of processing a key event."""

    consumed: bool = True           # Was the key handled?
    enter_insert: bool = False      # Should we enter insert mode?
    show_command_line: bool = False # Should we show command input?
    command_text: str = ""          # Pre-filled command text
    command_action: CommandAction | None = None  # Action from command mode
    message: str = ""               # Message to display to user


class VimEngine:
    """Main vim emulation controller.

    This class sits between key events and the TextArea, translating
    vim commands into TextArea operations.
    """

    def __init__(self, text_area: TextArea) -> None:
        self._text_area = text_area
        self._doc = DocumentWrapper(text_area)
        self._state = VimState()
        self._keymap = get_vim_keymap()

        # Buffer for multi-char sequences (gg, g_, etc.)
        self._key_buffer: str = ""

        # Pending char for f/t/F/T/r
        self._pending_char_cmd: str | None = None

        # Command mode handler
        self._command_handler = VimCommandHandler()

        # Callbacks for mode changes, command mode, etc.
        self._on_mode_change: Callable[[VimMode], None] | None = None
        self._on_command_mode: Callable[[str], None] | None = None
        self._on_command_update: Callable[[str], None] | None = None

    @property
    def mode(self) -> VimMode:
        """Current vim mode."""
        return self._state.mode

    @property
    def state(self) -> VimState:
        """Current vim state."""
        return self._state

    def set_mode_callback(self, callback: Callable[[VimMode], None]) -> None:
        """Set callback for mode changes."""
        self._on_mode_change = callback

    def set_command_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for command mode entry."""
        self._on_command_mode = callback

    def set_command_update_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for command line updates."""
        self._on_command_update = callback

    @property
    def command_buffer(self) -> str:
        """Get the current command buffer."""
        return self._command_handler.buffer

    def _notify_mode_change(self) -> None:
        """Notify callback of mode change."""
        if self._on_mode_change:
            self._on_mode_change(self._state.mode)

    # ─────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────

    def handle_key(self, key: str) -> KeyResult:
        """Process a key event.

        Args:
            key: The key that was pressed (e.g., "j", "d", "escape")

        Returns:
            KeyResult indicating how the key was handled
        """
        mode = self._state.mode

        # Handle based on current mode
        if mode == VimMode.INSERT:
            return self._handle_insert_mode(key)
        elif mode == VimMode.NORMAL:
            return self._handle_normal_mode(key)
        elif mode == VimMode.VISUAL:
            return self._handle_visual_mode(key)
        elif mode == VimMode.VISUAL_LINE:
            return self._handle_visual_line_mode(key)
        elif mode == VimMode.OPERATOR_PENDING:
            return self._handle_operator_pending(key)
        elif mode == VimMode.COMMAND:
            return self._handle_command_mode(key)

        return KeyResult(consumed=False)

    def enter_insert_mode(self) -> None:
        """Enter insert mode."""
        self._state.enter_mode(VimMode.INSERT)
        self._state.insert_start = self._doc.cursor_location
        self._notify_mode_change()

    def exit_insert_mode(self) -> None:
        """Exit insert mode, return to normal mode."""
        self._state.enter_mode(VimMode.NORMAL)
        # Move cursor back one (vim behavior)
        if self._doc.cursor_col > 0:
            self._doc.move_cursor(self._doc.get_cursor_left(1))
        self._notify_mode_change()

    def enter_visual_mode(self, line_mode: bool = False) -> None:
        """Enter visual mode."""
        anchor = self._doc.cursor_location
        if line_mode:
            self._state.start_visual(anchor, VimMode.VISUAL_LINE)
            # In visual line mode, immediately select the entire current line
            row = anchor[0]
            line_start = (row, 0)
            line_end = (row, len(self._doc.lines[row]))
            self._doc.move_cursor(line_start)
            self._doc.move_cursor(line_end, select=True)
        else:
            self._state.start_visual(anchor, VimMode.VISUAL)
        self._notify_mode_change()

    def exit_visual_mode(self) -> None:
        """Exit visual mode."""
        self._state.enter_mode(VimMode.NORMAL)
        # Clear selection by moving cursor to current position without selecting
        cursor = self._doc.cursor_location
        self._doc.move_cursor(cursor)
        self._notify_mode_change()

    def _clamp_cursor_to_document(self) -> None:
        """Ensure cursor is within document bounds (e.g., after undo/redo)."""
        row, col = self._doc.cursor_location
        line_count = self._doc.line_count

        # Clamp row to valid range
        if row >= line_count:
            row = max(0, line_count - 1)

        # Clamp column to valid range for the line
        if line_count > 0:
            line_len = len(self._doc.lines[row])
            # In normal mode, cursor stops at last char (line_len - 1)
            max_col = max(0, line_len - 1) if line_len > 0 else 0
            col = min(col, max_col)
        else:
            col = 0

        self._doc.move_cursor((row, col))

    # ─────────────────────────────────────────────────────────────────
    # Insert Mode
    # ─────────────────────────────────────────────────────────────────

    def _handle_insert_mode(self, key: str) -> KeyResult:
        """Handle keys in insert mode."""
        # Escape exits insert mode
        if key in ("escape", "ctrl+[", "ctrl+c"):
            self.exit_insert_mode()
            return KeyResult(consumed=True)

        # Let TextArea handle all other keys in insert mode
        return KeyResult(consumed=False)

    # ─────────────────────────────────────────────────────────────────
    # Normal Mode
    # ─────────────────────────────────────────────────────────────────

    def _handle_normal_mode(self, key: str) -> KeyResult:
        """Handle keys in normal mode."""
        # Handle pending character input (f, t, r, etc.)
        if self._pending_char_cmd:
            return self._handle_pending_char(key)

        # Handle multi-char sequences (gg, g_, etc.)
        if self._key_buffer:
            return self._handle_key_buffer(key)

        # Check for count prefix
        if self._state.accumulate_digit(key):
            return KeyResult(consumed=True)

        # Special case: 0 at start is motion, not count
        # (accumulate_digit returns False for 0 at start)

        # Look up the key in keymap
        binding = self._keymap.lookup(key, "normal")

        if binding is None:
            # Check for keys that start multi-char sequences
            if key == "g":
                self._key_buffer = "g"
                return KeyResult(consumed=True)
            return KeyResult(consumed=False)

        # Handle based on binding type
        if binding.type == BindingType.MOTION:
            return self._execute_motion(binding.handler)

        elif binding.type == BindingType.OPERATOR:
            return self._start_operator(binding.handler, key)

        elif binding.type == BindingType.ACTION:
            return self._execute_action(binding.handler)

        elif binding.type == BindingType.MODE_SWITCH:
            return self._execute_mode_switch(binding.handler)

        elif binding.type == BindingType.PENDING:
            self._pending_char_cmd = key
            return KeyResult(consumed=True)

        return KeyResult(consumed=False)

    def _handle_key_buffer(self, key: str) -> KeyResult:
        """Handle multi-character key sequences."""
        sequence = self._key_buffer + key
        self._key_buffer = ""

        # Look up the sequence
        binding = self._keymap.get_motion(sequence)
        if binding:
            return self._execute_motion(binding.handler)

        binding = self._keymap.get_operator(sequence)
        if binding:
            return self._start_operator(binding.handler, sequence)

        # Not a valid sequence
        return KeyResult(consumed=True)

    def _handle_pending_char(self, key: str) -> KeyResult:
        """Handle character input after f/t/F/T/r."""
        cmd = self._pending_char_cmd
        self._pending_char_cmd = None

        if len(key) != 1:
            # Invalid char (e.g., escape)
            return KeyResult(consumed=True)

        count = self._state.consume_count()

        if cmd == "f":
            result = motion_find_char(self._doc, self._state, count, key, forward=True, before=False)
        elif cmd == "F":
            result = motion_find_char(self._doc, self._state, count, key, forward=False, before=False)
        elif cmd == "t":
            result = motion_find_char(self._doc, self._state, count, key, forward=True, before=True)
        elif cmd == "T":
            result = motion_find_char(self._doc, self._state, count, key, forward=False, before=True)
        elif cmd == "r":
            # Replace character under cursor
            return self._replace_char(key)
        else:
            return KeyResult(consumed=True)

        if not result.failed:
            self._doc.move_cursor(result.position)

        return KeyResult(consumed=True)

    def _replace_char(self, char: str) -> KeyResult:
        """Replace character under cursor (r command)."""
        row, col = self._doc.cursor_location
        line = self._doc.current_line

        if col < len(line):
            start = (row, col)
            end = (row, col + 1)
            self._doc.replace_text(start, end, char)

        return KeyResult(consumed=True)

    # ─────────────────────────────────────────────────────────────────
    # Motion Execution
    # ─────────────────────────────────────────────────────────────────

    def _execute_motion(self, handler_name: str) -> KeyResult:
        """Execute a motion command."""
        handler = get_motion_handler(handler_name)
        if not handler:
            return KeyResult(consumed=False)

        count = self._state.consume_count()
        result = handler(self._doc, self._state, count)

        if not result.failed:
            self._doc.move_cursor(result.position)

        return KeyResult(consumed=True)

    # ─────────────────────────────────────────────────────────────────
    # Operator Handling
    # ─────────────────────────────────────────────────────────────────

    def _start_operator(self, handler_name: str, key: str) -> KeyResult:
        """Start an operator, waiting for motion/text object."""
        # Double operator (dd, yy, cc) operates on current line
        if self._state.pending_operator == key:
            return self._execute_line_operator(handler_name)

        self._state.pending_operator = key
        self._state.operator_count = self._state.consume_count()
        self._state.enter_mode(VimMode.OPERATOR_PENDING)

        return KeyResult(consumed=True)

    def _handle_operator_pending(self, key: str) -> KeyResult:
        """Handle keys while waiting for motion/text object."""
        # Escape cancels operator
        if key in ("escape", "ctrl+[", "ctrl+c"):
            self._state.reset_operator()
            self._state.enter_mode(VimMode.NORMAL)
            return KeyResult(consumed=True)

        # Check for count
        if self._state.accumulate_digit(key):
            return KeyResult(consumed=True)

        # Check for text object start (i or a)
        if key in ("i", "a"):
            self._key_buffer = key
            return KeyResult(consumed=True)

        # Handle text object completion
        if self._key_buffer in ("i", "a"):
            text_obj_key = self._key_buffer + key
            self._key_buffer = ""

            binding = self._keymap.get_text_object(text_obj_key)
            if binding:
                return self._execute_operator_with_text_object(binding.handler)

            # Invalid text object
            self._state.reset_operator()
            self._state.enter_mode(VimMode.NORMAL)
            return KeyResult(consumed=True)

        # Handle multi-char motion (gg)
        if key == "g":
            self._key_buffer = "g"
            return KeyResult(consumed=True)

        if self._key_buffer == "g":
            motion_key = "g" + key
            self._key_buffer = ""
            binding = self._keymap.get_motion(motion_key)
            if binding:
                return self._execute_operator_with_motion(binding.handler)
            self._state.reset_operator()
            self._state.enter_mode(VimMode.NORMAL)
            return KeyResult(consumed=True)

        # Check for motion
        binding = self._keymap.get_motion(key)
        if binding:
            return self._execute_operator_with_motion(binding.handler)

        # Check for pending char motion (f/t)
        pending_binding = self._keymap.get_pending(key)
        if pending_binding and key in ("f", "F", "t", "T"):
            self._pending_char_cmd = key
            return KeyResult(consumed=True)

        # Invalid key - cancel operator
        self._state.reset_operator()
        self._state.enter_mode(VimMode.NORMAL)
        return KeyResult(consumed=True)

    def _execute_operator_with_motion(self, motion_handler: str) -> KeyResult:
        """Execute pending operator with a motion."""
        motion_func = get_motion_handler(motion_handler)
        if not motion_func:
            self._state.reset_operator()
            self._state.enter_mode(VimMode.NORMAL)
            return KeyResult(consumed=True)

        count = self._state.get_effective_count()
        motion_result = motion_func(self._doc, self._state, count)

        if motion_result.failed:
            self._state.reset_operator()
            self._state.enter_mode(VimMode.NORMAL)
            return KeyResult(consumed=True)

        # Get the operator
        op_key = self._state.pending_operator
        op_binding = self._keymap.get_operator(op_key) if op_key else None

        if not op_binding:
            self._state.reset_operator()
            self._state.enter_mode(VimMode.NORMAL)
            return KeyResult(consumed=True)

        op_func = get_operator_handler(op_binding.handler)
        if not op_func:
            self._state.reset_operator()
            self._state.enter_mode(VimMode.NORMAL)
            return KeyResult(consumed=True)

        # Execute operator on range from cursor to motion target
        start = self._doc.cursor_location
        end = motion_result.position

        op_result = op_func(self._doc, self._state, start, end, motion_result.type)

        self._state.reset_operator()
        self._state.enter_mode(VimMode.NORMAL)

        if op_result.enter_insert:
            self.enter_insert_mode()
            return KeyResult(consumed=True, enter_insert=True)

        return KeyResult(consumed=True)

    def _execute_operator_with_text_object(self, textobj_handler: str) -> KeyResult:
        """Execute pending operator with a text object."""
        textobj_func = get_text_object_handler(textobj_handler)
        if not textobj_func:
            self._state.reset_operator()
            self._state.enter_mode(VimMode.NORMAL)
            return KeyResult(consumed=True)

        count = self._state.get_effective_count()
        textobj_result = textobj_func(self._doc, self._state, count)

        if textobj_result.failed:
            self._state.reset_operator()
            self._state.enter_mode(VimMode.NORMAL)
            return KeyResult(consumed=True)

        # Get the operator
        op_key = self._state.pending_operator
        op_binding = self._keymap.get_operator(op_key) if op_key else None

        if not op_binding:
            self._state.reset_operator()
            self._state.enter_mode(VimMode.NORMAL)
            return KeyResult(consumed=True)

        op_func = get_operator_handler(op_binding.handler)
        if not op_func:
            self._state.reset_operator()
            self._state.enter_mode(VimMode.NORMAL)
            return KeyResult(consumed=True)

        # Execute operator on text object range
        op_result = op_func(
            self._doc, self._state,
            textobj_result.start, textobj_result.end,
            textobj_result.type
        )

        self._state.reset_operator()
        self._state.enter_mode(VimMode.NORMAL)

        if op_result.enter_insert:
            self.enter_insert_mode()
            return KeyResult(consumed=True, enter_insert=True)

        return KeyResult(consumed=True)

    def _execute_line_operator(self, handler_name: str) -> KeyResult:
        """Execute operator on current line (dd, yy, cc)."""
        op_func = get_operator_handler(handler_name)
        if not op_func:
            self._state.reset_operator()
            self._state.enter_mode(VimMode.NORMAL)
            return KeyResult(consumed=True)

        count = self._state.get_effective_count()
        row = self._doc.cursor_row

        # Operate on count lines starting from current
        start = (row, 0)
        end = (min(row + count - 1, self._doc.line_count - 1), 0)

        op_result = op_func(self._doc, self._state, start, end, TextObjectType.LINEWISE)

        self._state.reset_operator()
        self._state.enter_mode(VimMode.NORMAL)

        if op_result.enter_insert:
            self.enter_insert_mode()
            return KeyResult(consumed=True, enter_insert=True)

        return KeyResult(consumed=True)

    # ─────────────────────────────────────────────────────────────────
    # Actions
    # ─────────────────────────────────────────────────────────────────

    def _execute_action(self, handler_name: str) -> KeyResult:
        """Execute an immediate action."""
        count = self._state.consume_count()

        if handler_name == "action_insert":
            self.enter_insert_mode()
            return KeyResult(consumed=True, enter_insert=True)

        elif handler_name == "action_insert_line_start":
            self._doc.move_cursor(self._doc.get_first_non_blank())
            self.enter_insert_mode()
            return KeyResult(consumed=True, enter_insert=True)

        elif handler_name == "action_append":
            # Move right one char, then insert
            # Note: Can't use get_cursor_right here since it's limited to line_length-1
            # For append, we need to allow cursor at line_length (after last char)
            row, col = self._doc.cursor_location
            line_len = self._doc.current_line_length
            new_col = min(col + 1, line_len)  # Allow going to end of line
            self._doc.move_cursor((row, new_col))
            self.enter_insert_mode()
            return KeyResult(consumed=True, enter_insert=True)

        elif handler_name == "action_append_line_end":
            self._doc.move_cursor((self._doc.cursor_row, self._doc.current_line_length))
            self.enter_insert_mode()
            return KeyResult(consumed=True, enter_insert=True)

        elif handler_name == "action_open_below":
            # Insert new line below and enter insert mode
            row = self._doc.cursor_row
            line_end = (row, self._doc.current_line_length)
            self._doc.move_cursor(line_end)
            self._doc.insert_text("\n")
            self.enter_insert_mode()
            return KeyResult(consumed=True, enter_insert=True)

        elif handler_name == "action_open_above":
            # Insert new line above and enter insert mode
            row = self._doc.cursor_row
            if row == 0:
                self._doc.move_cursor((0, 0))
                self._doc.insert_text("\n")
                self._doc.move_cursor((0, 0))
            else:
                prev_line_end = (row - 1, len(self._doc.lines[row - 1]))
                self._doc.move_cursor(prev_line_end)
                self._doc.insert_text("\n")
            self.enter_insert_mode()
            return KeyResult(consumed=True, enter_insert=True)

        elif handler_name == "action_substitute":
            # Delete char and enter insert mode
            row, col = self._doc.cursor_location
            line = self._doc.current_line
            if col < len(line):
                self._doc.delete_range((row, col), (row, col + 1))
            self.enter_insert_mode()
            return KeyResult(consumed=True, enter_insert=True)

        elif handler_name == "action_substitute_line":
            # Delete line contents and enter insert mode
            row = self._doc.cursor_row
            line = self._doc.current_line
            # Keep indentation
            indent = len(line) - len(line.lstrip())
            self._doc.delete_range((row, indent), (row, len(line)))
            self._doc.move_cursor((row, indent))
            self.enter_insert_mode()
            return KeyResult(consumed=True, enter_insert=True)

        elif handler_name == "action_change_to_eol":
            # C = c$
            row = self._doc.cursor_row
            col = self._doc.cursor_col
            line_len = self._doc.current_line_length
            if col < line_len:
                deleted = self._doc.delete_range((row, col), (row, line_len))
                self._state.yank_to_register(deleted)
            self.enter_insert_mode()
            return KeyResult(consumed=True, enter_insert=True)

        elif handler_name == "action_delete_to_eol":
            # D = d$
            row = self._doc.cursor_row
            col = self._doc.cursor_col
            line_len = self._doc.current_line_length
            if col < line_len:
                deleted = self._doc.delete_range((row, col), (row, line_len))
                self._state.yank_to_register(deleted)
            return KeyResult(consumed=True)

        elif handler_name == "action_delete_char":
            # x = delete char under cursor
            row, col = self._doc.cursor_location
            line = self._doc.current_line
            for _ in range(count):
                if col < len(line):
                    deleted = self._doc.delete_range((row, col), (row, col + 1))
                    self._state.yank_to_register(deleted)
                    line = self._doc.current_line
            return KeyResult(consumed=True)

        elif handler_name == "action_delete_char_before":
            # X = delete char before cursor
            row, col = self._doc.cursor_location
            for _ in range(count):
                if col > 0:
                    deleted = self._doc.delete_range((row, col - 1), (row, col))
                    self._state.yank_to_register(deleted)
                    col -= 1
            return KeyResult(consumed=True)

        elif handler_name == "action_paste_after":
            reg = self._state.get_register_content()
            if reg.content:
                if reg.linewise:
                    # Paste on new line below
                    row = self._doc.cursor_row
                    line_end = (row, self._doc.current_line_length)
                    self._doc.move_cursor(line_end)
                    self._doc.insert_text("\n" + reg.content)
                else:
                    # Paste after cursor
                    row, col = self._doc.cursor_location
                    if col < self._doc.current_line_length:
                        col += 1
                    self._doc.move_cursor((row, col))
                    self._doc.insert_text(reg.content)
            return KeyResult(consumed=True)

        elif handler_name == "action_paste_before":
            reg = self._state.get_register_content()
            if reg.content:
                if reg.linewise:
                    # Paste on new line above
                    row = self._doc.cursor_row
                    if row == 0:
                        self._doc.move_cursor((0, 0))
                        self._doc.insert_text(reg.content + "\n")
                        self._doc.move_cursor((0, 0))
                    else:
                        prev_end = (row - 1, len(self._doc.lines[row - 1]))
                        self._doc.move_cursor(prev_end)
                        self._doc.insert_text("\n" + reg.content)
                else:
                    # Paste before cursor
                    self._doc.insert_text(reg.content)
            return KeyResult(consumed=True)

        elif handler_name == "action_undo":
            # Delegate to TextArea's undo
            # Clamp cursor BEFORE undo to avoid Textual internal errors
            self._clamp_cursor_to_document()
            try:
                self._text_area.undo()
            except (ValueError, IndexError):
                # TextArea can throw if cursor is out of bounds during undo
                pass
            # Clamp cursor after undo (document may have shrunk)
            self._clamp_cursor_to_document()
            return KeyResult(consumed=True)

        elif handler_name == "action_redo":
            # Delegate to TextArea's redo
            self._clamp_cursor_to_document()
            try:
                self._text_area.redo()
            except (ValueError, IndexError):
                pass
            self._clamp_cursor_to_document()
            return KeyResult(consumed=True)

        elif handler_name == "action_join_lines":
            row = self._doc.cursor_row
            if row < self._doc.line_count - 1:
                # Join current line with next
                line_end = (row, self._doc.current_line_length)
                next_line_start = (row + 1, 0)
                # Find first non-space of next line
                next_line = self._doc.lines[row + 1]
                first_non_space = 0
                while first_non_space < len(next_line) and next_line[first_non_space].isspace():
                    first_non_space += 1

                # Delete newline and leading whitespace, replace with single space
                self._doc.delete_range(line_end, (row + 1, first_non_space))
                self._doc.move_cursor(line_end)
                self._doc.insert_text(" ")
            return KeyResult(consumed=True)

        elif handler_name == "action_swap_case_char":
            row, col = self._doc.cursor_location
            line = self._doc.current_line
            if col < len(line):
                char = line[col]
                swapped = char.lower() if char.isupper() else char.upper()
                self._doc.replace_text((row, col), (row, col + 1), swapped)
                # Move right
                if col < len(line) - 1:
                    self._doc.move_cursor((row, col + 1))
            return KeyResult(consumed=True)

        elif handler_name == "action_escape":
            if self._state.mode != VimMode.NORMAL:
                self._state.enter_mode(VimMode.NORMAL)
                self._notify_mode_change()
            return KeyResult(consumed=True)

        return KeyResult(consumed=False)

    # ─────────────────────────────────────────────────────────────────
    # Mode Switches
    # ─────────────────────────────────────────────────────────────────

    def _execute_mode_switch(self, handler_name: str) -> KeyResult:
        """Execute a mode switch command."""
        if handler_name == "mode_visual":
            self.enter_visual_mode(line_mode=False)
            return KeyResult(consumed=True)

        elif handler_name == "mode_visual_line":
            self.enter_visual_mode(line_mode=True)
            return KeyResult(consumed=True)

        elif handler_name == "mode_command":
            self.enter_command_mode()
            return KeyResult(consumed=True, show_command_line=True, command_text=":")

        return KeyResult(consumed=False)

    # ─────────────────────────────────────────────────────────────────
    # Visual Mode
    # ─────────────────────────────────────────────────────────────────

    def _handle_visual_mode(self, key: str) -> KeyResult:
        """Handle keys in visual mode."""
        # Handle multi-char sequences (gg, G, etc.)
        if self._key_buffer:
            return self._handle_visual_key_buffer(key)

        # Check for count prefix (e.g., 10j to move down 10 lines)
        if self._state.accumulate_digit(key):
            return KeyResult(consumed=True)

        # Escape exits visual mode
        if key in ("escape", "ctrl+[", "ctrl+c"):
            self.exit_visual_mode()
            return KeyResult(consumed=True)

        # v toggles back to normal
        if key == "v":
            self.exit_visual_mode()
            return KeyResult(consumed=True)

        # V switches to visual line
        if key == "V":
            self._state.enter_mode(VimMode.VISUAL_LINE)
            self._notify_mode_change()
            return KeyResult(consumed=True)

        # Visual mode actions (i/a enter insert at selection boundary)
        binding = self._keymap.get_visual_action(key)
        if binding:
            return self._execute_visual_action(binding.handler)

        # x and s in visual mode act as delete/change operators
        if key == "x":
            return self._execute_visual_operator("operator_delete")
        if key == "s":
            return self._execute_visual_operator("operator_change")

        # Operators act on selection
        binding = self._keymap.get_operator(key)
        if binding:
            return self._execute_visual_operator(binding.handler)

        # Start multi-char sequence
        if key == "g":
            self._key_buffer = "g"
            return KeyResult(consumed=True)

        # Motions extend selection
        binding = self._keymap.get_motion(key)
        if binding:
            return self._execute_visual_motion(binding.handler)

        return KeyResult(consumed=False)

    def _handle_visual_line_mode(self, key: str) -> KeyResult:
        """Handle keys in visual line mode."""
        # Handle multi-char sequences (gg, G, etc.)
        if self._key_buffer:
            return self._handle_visual_key_buffer(key)

        # Check for count prefix (e.g., 10j to move down 10 lines)
        if self._state.accumulate_digit(key):
            return KeyResult(consumed=True)

        # Most handling same as visual mode
        if key in ("escape", "ctrl+[", "ctrl+c"):
            self.exit_visual_mode()
            return KeyResult(consumed=True)

        if key == "V":
            self.exit_visual_mode()
            return KeyResult(consumed=True)

        if key == "v":
            self._state.enter_mode(VimMode.VISUAL)
            self._notify_mode_change()
            return KeyResult(consumed=True)

        # Visual line mode actions (i/a enter insert at selection boundary)
        binding = self._keymap.get_visual_action(key)
        if binding:
            return self._execute_visual_action(binding.handler, linewise=True)

        # x and s in visual line mode act as delete/change operators
        if key == "x":
            return self._execute_visual_operator("operator_delete", linewise=True)
        if key == "s":
            return self._execute_visual_operator("operator_change", linewise=True)

        binding = self._keymap.get_operator(key)
        if binding:
            return self._execute_visual_operator(binding.handler, linewise=True)

        # Start multi-char sequence
        if key == "g":
            self._key_buffer = "g"
            return KeyResult(consumed=True)

        binding = self._keymap.get_motion(key)
        if binding:
            return self._execute_visual_motion(binding.handler)

        return KeyResult(consumed=False)

    def _handle_visual_key_buffer(self, key: str) -> KeyResult:
        """Handle multi-char key sequences in visual modes (gg, g_, etc.)."""
        sequence = self._key_buffer + key
        self._key_buffer = ""

        # Look up the sequence as a motion
        binding = self._keymap.get_motion(sequence)
        if binding:
            return self._execute_visual_motion(binding.handler)

        # Not a valid sequence, consume and ignore
        return KeyResult(consumed=True)

    def _execute_visual_motion(self, handler_name: str) -> KeyResult:
        """Execute motion to extend visual selection."""
        handler = get_motion_handler(handler_name)
        if not handler:
            return KeyResult(consumed=False)

        count = self._state.consume_count()
        result = handler(self._doc, self._state, count)

        if not result.failed:
            if self._state.mode == VimMode.VISUAL_LINE:
                # In visual line mode, select full lines from anchor to destination
                anchor = self._state.visual_anchor
                if anchor is not None:
                    anchor_row = anchor[0]
                    dest_row = result.position[0]

                    if anchor_row <= dest_row:
                        # Selecting downward: anchor at top, cursor at bottom
                        sel_anchor = (anchor_row, 0)
                        sel_cursor = (dest_row, len(self._doc.lines[dest_row]))
                    else:
                        # Selecting upward: anchor at bottom, cursor at top
                        sel_anchor = (anchor_row, len(self._doc.lines[anchor_row]))
                        sel_cursor = (dest_row, 0)

                    # Use set_selection for atomic update (avoids cursor position issues)
                    self._doc.set_selection(sel_anchor, sel_cursor)
                else:
                    self._doc.move_cursor(result.position, select=True)
            else:
                self._doc.move_cursor(result.position, select=True)

        return KeyResult(consumed=True)

    def _execute_visual_operator(self, handler_name: str, linewise: bool = False) -> KeyResult:
        """Execute operator on visual selection."""
        op_func = get_operator_handler(handler_name)
        if not op_func:
            self.exit_visual_mode()
            return KeyResult(consumed=True)

        anchor = self._state.visual_anchor
        cursor = self._doc.cursor_location

        if anchor is None:
            self.exit_visual_mode()
            return KeyResult(consumed=True)

        start = min(anchor, cursor)
        end = max(anchor, cursor)

        obj_type = TextObjectType.LINEWISE if linewise else TextObjectType.INCLUSIVE

        op_result = op_func(self._doc, self._state, start, end, obj_type)

        self.exit_visual_mode()

        if op_result.enter_insert:
            self.enter_insert_mode()
            return KeyResult(consumed=True, enter_insert=True)

        return KeyResult(consumed=True)

    def _execute_visual_action(self, handler_name: str, linewise: bool = False) -> KeyResult:
        """Execute visual action (i/a to enter insert at selection boundary)."""
        anchor = self._state.visual_anchor
        cursor = self._doc.cursor_location

        if anchor is None:
            self.exit_visual_mode()
            return KeyResult(consumed=True)

        start = min(anchor, cursor)
        end = max(anchor, cursor)

        # Calculate target position before exiting visual mode
        if handler_name == "action_visual_insert":
            # Insert at start of selection
            if linewise:
                target_pos = (start[0], 0)
            else:
                target_pos = start
        elif handler_name == "action_visual_append":
            # Append after end of selection
            if linewise:
                end_row = end[0]
                line_len = len(self._doc.lines[end_row])
                target_pos = (end_row, line_len)
            else:
                end_row, end_col = end
                line_len = len(self._doc.lines[end_row])
                # Move to position after the last selected character
                target_pos = (end_row, min(end_col + 1, line_len))
        else:
            target_pos = cursor

        # Exit visual mode first (clears selection)
        self.exit_visual_mode()
        # Then move cursor to target position
        self._doc.move_cursor(target_pos)
        self.enter_insert_mode()
        return KeyResult(consumed=True, enter_insert=True)

    # ─────────────────────────────────────────────────────────────────
    # Command Mode
    # ─────────────────────────────────────────────────────────────────

    def _handle_command_mode(self, key: str) -> KeyResult:
        """Handle keys in command mode."""
        # Escape cancels command mode
        if key in ("escape", "ctrl+[", "ctrl+c"):
            self._command_handler.cancel()
            self._state.enter_mode(VimMode.NORMAL)
            self._notify_mode_change()
            return KeyResult(consumed=True)

        # Enter executes the command
        if key == "enter":
            result = self._command_handler.execute()
            self._state.enter_mode(VimMode.NORMAL)
            self._notify_mode_change()
            return KeyResult(
                consumed=True,
                command_action=result.action,
                message=result.message,
            )

        # Backspace
        if key == "backspace":
            if not self._command_handler.backspace():
                # Buffer is empty, exit command mode
                self._state.enter_mode(VimMode.NORMAL)
                self._notify_mode_change()
            else:
                self._notify_command_update()
            return KeyResult(consumed=True)

        # Regular character input
        if len(key) == 1:
            self._command_handler.add_char(key)
            self._notify_command_update()
            return KeyResult(consumed=True)

        return KeyResult(consumed=True)

    def _notify_command_update(self) -> None:
        """Notify callback of command buffer update."""
        if self._on_command_update:
            self._on_command_update(":" + self._command_handler.buffer)

    def enter_command_mode(self) -> None:
        """Enter command mode."""
        self._command_handler.start()
        self._state.enter_mode(VimMode.COMMAND)
        self._notify_mode_change()
        if self._on_command_mode:
            self._on_command_mode(":")
