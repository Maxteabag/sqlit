# Custom Keymaps

sqlit lets you remap the keys that trigger any action. The set of actions and the states they live in is fixed by the app; the keymap JSON is *purely* a key-remapping layer on top of the defaults.

## Quick start

1. Create the keymaps directory and copy the template:
   ```bash
   mkdir -p ~/.config/sqlit/keymaps
   cp config/keymap.template.json ~/.config/sqlit/keymaps/my-custom.json
   ```

2. Edit `~/.config/sqlit/keymaps/my-custom.json`. Only list the bindings you want to change.

3. Enable it by adding to `~/.config/sqlit/settings.json`:
   ```json
   { "custom_keymap": "my-custom" }
   ```
   Use the filename without `.json`. To revert, set `"custom_keymap": "default"` or remove the key.

4. Restart sqlit. The footer and help screen (`?`) reflect your custom keys automatically.

## File shape

The JSON mirrors the state machine: each binding lives in the state (for action keys) or menu (for leader commands) where it is active.

```json
{
  "keymap": {
    "action_keys": {
      "<state>": {
        "<action>": "<key>"
      }
    },
    "leader_commands": {
      "<menu>": {
        "<action>": "<key>"
      }
    }
  }
}
```

Values can be a single key string, or a list to provide aliases (the first entry is the primary key shown in footer/help):

```json
"tree": {
  "refresh_tree": ["f", "R"]
}
```

A single string *replaces every default key* for that action in that state. A list lets you control the full set of keys explicitly. **Set the value to `null` to unbind a default entirely** — useful when you want to claim a key that already has a default action:

```json
"query_normal": {
  "enter_insert_mode": "u",
  "undo": null
}
```

Here `u` enters insert mode and the default `u → undo` binding is removed (no key triggers undo in `query_normal` anymore). Without the `undo: null`, the loader would reject the keymap because two actions would be claiming `u`.

## What you can change — and what you cannot

You can change **which key** triggers a given action. That is the entire vocabulary.

You cannot — and don't need to — set the action's label, category, guard, priority, or visibility. Those are properties of the action itself, defined in `sqlit/core/keymap.py`. The keymap is strictly a key-rebinding layer.

You also cannot invent new actions or attach an existing action to a state it doesn't belong to. The loader rejects unknown `(state, action)` pairs with a clear error that lists the known actions for that state.

## Validation at startup

The keymap is checked before the app boots. Failures fall back to defaults; the error surfaces as a Textual notification in the running app, and as a `[sqlit] …` line on stderr when running headless. Possible failures:

- **Unknown action in a state** — sqlit lists the actions that *do* exist in that state.
- **Conflicting bindings** — two different actions claiming the same key in the same state (or the same menu, for leader commands). Default-only overlaps that are disambiguated by runtime state — e.g. `d` on a connection vs. on a folder, both in `tree` — are tolerated; only collisions you introduce are flagged.

## States (for `action_keys`)

| State | Where it applies |
|-------|------------------|
| `global` | Active everywhere |
| `navigation` | Switching focus between the three panes |
| `tree` | Database explorer tree |
| `tree_filter` | Filter input over the explorer tree |
| `tree_visual` | Tree visual selection mode |
| `query_normal` | Query editor, NORMAL mode |
| `query_insert` | Query editor, INSERT mode |
| `autocomplete` | Autocomplete dropdown is visible |
| `results` | Results table |
| `results_filter` | Filter input over the results table |
| `value_view` | Value-view modal |

## Menus (for `leader_commands`)

`leader` (the top-level command menu), plus the vim-style sub-menus: `delete`, `yank`, `change`, `g`, `gc` (line comments), `ry` (results yank), `rye` (results export), `vy` (value-view yank).

## Action catalog

The canonical list lives in `sqlit/core/keymap.py` — `DefaultKeymapProvider._build_action_keys()` and `_build_leader_commands()`. Use the in-app help (`?`) or read the source for the full set. The most commonly-rebound ones:

**Global** — `leader_key`, `show_help`, `quit`, `cancel_operation`, `enter_command_mode`

**Navigation** — `focus_explorer`, `focus_query`, `focus_results`

**Tree** — `tree_cursor_up`, `tree_cursor_down`, `select_table`, `tree_filter`, `collapse_tree`, `refresh_tree`, `new_connection`, `edit_connection`, `delete_connection`, `duplicate_connection`, `disconnect`

**Query (normal mode)** — `enter_insert_mode`, `prepend_insert_mode`, `append_insert_mode`, `append_line_end`, `open_line_below`, `open_line_above`, `execute_query`, `cursor_left`, `cursor_down`, `cursor_up`, `cursor_right`, `cursor_word_forward`, `cursor_WORD_forward`, `cursor_word_back`, `cursor_WORD_back`, `cursor_line_start`, `cursor_line_end`, `cursor_last_line`, `cursor_find_char`, `cursor_find_char_back`, `cursor_till_char`, `cursor_till_char_back`, `cursor_matching_bracket`, `paste`, `show_history`, `new_query`, `undo`, `redo`

**Query (insert mode)** — `exit_insert_mode`, `execute_query_insert`, `autocomplete_accept`, `select_all`, `copy_selection`, `paste`

**Autocomplete** — `autocomplete_next`, `autocomplete_prev`, `autocomplete_accept`, `autocomplete_close`

**Results** — `view_cell`, `view_cell_full`, `edit_cell`, `delete_row`, `clear_results`, `results_filter`, `results_cursor_left/down/up/right`, `next_result_section`, `prev_result_section`, `toggle_result_section`

**Value view** — `close_value_view`, `copy_value_view`, `toggle_value_view_mode`, `collapse_all_json_nodes`, `expand_all_json_nodes`

## Special key names

`space`, `escape`, `enter`, `backspace`, `delete`, `tab`, `question_mark`, `slash`, `dollar_sign`, `percent_sign`, `asterisk`, `ctrl+<key>`, `shift+<key>`.

## Example

Rebind autocomplete to `ctrl+n`/`ctrl+p`, swap `<leader>h` to `<leader>?`, keep the arrow-key aliases for tree navigation, and use `ctrl+enter` to execute queries in normal mode:

```json
{
  "keymap": {
    "action_keys": {
      "query_normal": {
        "execute_query": "ctrl+enter"
      },
      "autocomplete": {
        "autocomplete_next": "ctrl+n",
        "autocomplete_prev": "ctrl+p"
      },
      "tree": {
        "tree_cursor_down": ["j", "down"],
        "tree_cursor_up":   ["k", "up"]
      }
    },
    "leader_commands": {
      "leader": {
        "show_help": "question_mark"
      }
    }
  }
}
```

## Troubleshooting

**Keymap didn't load.** Check `~/.config/sqlit/settings.json` — `custom_keymap` must match your filename without the `.json`. The app shows a notification on startup; running headless prints `[sqlit] Failed to load custom keymap …` to stderr.

**"Unknown action" error.** The action doesn't exist in the state you named. The error message lists the known actions for that state — pick one of those, or check the canonical list in `sqlit/core/keymap.py`.

**"Conflicting keybindings" error.** Your overrides bind the same key to two different actions in the same state. Pick a different key, or unbind the colliding default by setting its key to `null` (e.g. `"undo": null`).

**Invalid JSON.** Run `python -m json.tool ~/.config/sqlit/keymaps/my-custom.json` to find the syntax error.
