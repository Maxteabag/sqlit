# mypy Error Summary

## Files with Most Errors
```
12 errors - sqlit/ui/mixins/tree.py
10 errors - sqlit/ui/screens/connection.py
 7 errors - sqlit/commands.py
 6 errors - sqlit/db/adapters/ (various)
 4 errors - sqlit/app.py
```

## Error Types

### 1. no-untyped-def (40 errors)
Functions missing parameter type annotations.

**Example:**
```python
# Before
def on_button_pressed(event):
    ...

# After
def on_button_pressed(event: Button.Pressed) -> None:
    ...
```

### 2. attr-defined (38 errors)
Missing attributes in Protocol or enum issues.

**Common ones:**
- `DatabaseType.MSSQL` - enum member access
- Missing Protocol attributes

### 3. return-value (20 errors)
Wrong return type annotations.

**Example:**
```python
# Wrong
def cursor(self) -> None:
    return MockCursor()  # Error!

# Fixed
def cursor(self) -> MockCursor:
    return MockCursor()
```

### 4. no-any-return (11 errors)
Functions returning `Any` but declared to return specific type.

**Example:**
```python
# In adapters
def get_row_count(self, cursor: Any) -> int:
    return cursor.rowcount  # rowcount is Any type
```

## Quick Fixes

Run in Neovim:
1. `:Telescope diagnostics` - Browse all errors
2. `:lua vim.diagnostic.open_float()` - Show error under cursor
3. `gd` - Go to definition
4. `K` - Show hover info

## Full Error List
See: mypy-errors.txt (177 errors across 31 files)
