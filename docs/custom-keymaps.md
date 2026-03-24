# Custom Keymaps

sqlit supports custom keymaps, allowing you to customize all keyboard shortcuts to match your preferences.

## Quick Start

1. **Copy the template:**
   ```bash
   mkdir -p ~/.sqlit/keymaps
   cp config/keymap.template.json ~/.sqlit/keymaps/my-custom.json
   ```

2. **Edit the keymap:**
   Open `~/.sqlit/keymaps/my-custom.json` and customize the keybindings.

3. **Enable your custom keymap:**
   Edit `~/.sqlit/settings.json` and set:
   ```json
   {
     "custom_keymap": "my-custom"
   }
   ```
   Note: Use the filename without the `.json` extension.

4. **Restart sqlit** to load your custom keymap.

## Keymap Structure

Custom keymaps are JSON files with two main sections:

### Leader Commands

Leader commands are triggered by pressing the leader key (default: `space`) followed by another key.

```json
{
  "keymap": {
    "leader_commands": [
      {
        "key": "q",
        "action": "quit",
        "label": "Quit",
        "category": "Actions",
        "guard": null,
        "menu": "leader"
      }
    ]
  }
}
```

**Fields:**
- `key` (required): The key to press after the leader key
- `action` (required): The action to execute
- `label` (required): Display label in the help menu
- `category` (required): Category for grouping in help menu
- `guard` (optional): Condition that must be met (e.g., `"has_connection"`)
- `menu` (optional): Menu ID (default: `"leader"`)

### Action Keys

Action keys are direct keybindings that work in specific contexts.

```json
{
  "keymap": {
    "action_keys": [
      {
        "key": "i",
        "action": "enter_insert_mode",
        "context": "query_normal",
        "guard": null,
        "primary": true,
        "show": false,
        "priority": false
      }
    ]
  }
}
```

**Fields:**
- `key` (required): The key combination (e.g., `"i"`, `"ctrl+q"`, `"escape"`)
- `action` (required): The action to execute
- `context` (optional): Context where this binding is active (e.g., `"query_normal"`, `"tree"`, `"results"`)
- `guard` (optional): Condition that must be met
- `primary` (optional): Whether this is the primary binding for the action (default: `true`)
- `show` (optional): Whether to show in Textual's binding hints (default: `false`)
- `priority` (optional): Whether to give priority to this binding (default: `false`)

## Special Key Names

Some keys use special names in the keymap:

- `space` - Space bar
- `escape` - Escape key
- `enter` - Enter/Return key
- `backspace` - Backspace key
- `delete` - Delete key
- `tab` - Tab key
- `question_mark` - ? key
- `slash` - / key
- `dollar_sign` - $ key
- `percent_sign` - % key
- `asterisk` - * key
- `ctrl+<key>` - Ctrl key combinations (e.g., `"ctrl+q"`, `"ctrl+enter"`)
- `shift+<key>` - Shift key combinations (e.g., `"shift+tab"`)

## Common Actions

### Global Actions
- `quit` - Exit sqlit
- `show_help` - Show help menu
- `cancel_operation` - Cancel current operation
- `leader_key` - Trigger leader menu

### Navigation Actions
- `focus_explorer` - Focus the database explorer
- `focus_query` - Focus the query editor
- `focus_results` - Focus the results table

### Connection Actions
- `show_connection_picker` - Show connection picker
- `disconnect` - Disconnect from database
- `new_connection` - Create new connection

### Query Editor Actions (Normal Mode)
- `enter_insert_mode` - Enter insert mode
- `prepend_insert_mode` - Enter insert mode at line start
- `append_insert_mode` - Enter insert mode after cursor
- `append_line_end` - Enter insert mode at line end
- `open_line_below` - Open new line below and enter insert mode
- `open_line_above` - Open new line above and enter insert mode
- `execute_query` - Execute the query

### Query Editor Actions (Insert Mode)
- `exit_insert_mode` - Return to normal mode
- `execute_query_insert` - Execute query from insert mode

### Vim-style Navigation
- `cursor_left`, `cursor_down`, `cursor_up`, `cursor_right` - Move cursor
- `cursor_word_forward` - Move to next word
- `cursor_word_back` - Move to previous word
- `cursor_line_start` - Move to line start
- `cursor_line_end` - Move to line end
- `cursor_last_line` - Move to last line

### Results Actions
- `view_cell` - View cell value
- `edit_cell` - Edit cell value
- `delete_row` - Delete row
- `results_yank_leader_key` - Trigger results copy menu
- `clear_results` - Clear results
- `results_filter` - Filter results

## Contexts

Action keys can be scoped to specific contexts:

- `global` - Active everywhere
- `query_normal` - Query editor in normal mode
- `query_insert` - Query editor in insert mode
- `tree` - Database explorer tree
- `results` - Results table
- `navigation` - For navigation actions
- `autocomplete` - Autocomplete dropdown

## Guards

Guards are conditions that must be met for a keybinding to be active:

- `has_connection` - Database is connected
- `query_executing` - Query is currently executing

## Examples

### Vim-style Leader Key

Change the leader key from space to comma:

```json
{
  "keymap": {
    "action_keys": [
      {
        "key": "comma",
        "action": "leader_key",
        "context": "global",
        "primary": true,
        "priority": true
      }
    ]
  }
}
```

### Emacs-style Bindings

Use Ctrl+X Ctrl+C to quit instead of `<space>q`:

```json
{
  "keymap": {
    "leader_commands": [],
    "action_keys": [
      {
        "key": "ctrl+x",
        "action": "leader_key",
        "context": "global",
        "primary": true,
        "priority": true
      }
    ]
  }
}
```

Then add a leader command:
```json
{
  "key": "ctrl+c",
  "action": "quit",
  "label": "Quit",
  "category": "Actions",
  "menu": "leader"
}
```

### Custom Query Execution

Execute query with Ctrl+Enter in normal mode:

```json
{
  "keymap": {
    "action_keys": [
      {
        "key": "ctrl+enter",
        "action": "execute_query",
        "context": "query_normal",
        "primary": true
      }
    ]
  }
}
```

## Troubleshooting

### Keymap not loading

1. Check that `custom_keymap` in `~/.sqlit/settings.json` matches your filename (without `.json`)
2. Check console output for error messages: `sqlit 2>&1 | grep keymap`
3. Verify JSON syntax with: `python -m json.tool ~/.sqlit/keymaps/my-custom.json`

### Invalid JSON

If sqlit reports JSON errors, validate your file:

```bash
python -m json.tool ~/.sqlit/keymaps/my-custom.json > /dev/null
```

### Missing required fields

Each leader command must have: `key`, `action`, `label`, `category`
Each action key must have: `key`, `action`

## Resetting to Default

To revert to the default keymap, set in `~/.sqlit/settings.json`:

```json
{
  "custom_keymap": "default"
}
```

Or remove the `custom_keymap` field entirely.

## Complete Example

See `config/keymap.template.json` for a complete example with all common keybindings.
