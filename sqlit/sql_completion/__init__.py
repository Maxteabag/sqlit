"""SQL completion engine.

Provides intelligent SQL autocompletion with:
- Context-aware suggestions (tables after FROM, columns after SELECT, etc.)
- Alias recognition (FROM users u -> u.id suggests users columns)
- Fuzzy matching
- SQL keywords and common functions
- Statement-specific handling (INSERT, UPDATE, DELETE)
"""

from .completion import get_completions, get_context
from .core import (
    RESERVED_WORDS,
    SQL_FUNCTIONS,
    SQL_KEYWORDS,
    SQL_OPERATORS,
    Suggestion,
    SuggestionType,
    TableRef,
    build_alias_map,
    extract_cte_names,
    extract_table_refs,
    find_context_keyword,
    find_current_clause,
    find_last_keyword,
    fuzzy_match,
    get_all_functions,
    get_all_keywords,
    get_current_word,
    is_inside_string,
    remove_comments,
    remove_string_literals,
)
from .alter_table import ALTER_OPERATIONS, get_alter_table_completions, get_alter_table_context
from .create_index import get_create_index_completions
from .create_table import (
    SQL_CONSTRAINTS,
    SQL_DATA_TYPES,
    SQL_TABLE_CONSTRAINTS,
    get_create_table_completions,
    get_create_table_context,
)
from .create_view import get_create_view_completions
from .delete import extract_delete_table_refs, get_delete_context
from .drop import DROP_OBJECTS, get_drop_completions, get_drop_context
from .insert import get_insert_context
from .truncate import get_truncate_completions
from .update import get_update_context

# Backwards compatibility aliases for private functions
_is_inside_string = is_inside_string
_get_last_token_info = None  # Internal to completion.py
_remove_string_literals = remove_string_literals
_remove_comments = remove_comments
_find_context_keyword = find_context_keyword
_find_last_keyword = find_last_keyword
_find_current_clause = find_current_clause
_get_current_word = get_current_word
_build_alias_map = build_alias_map

__all__ = [
    # Main API
    "get_completions",
    "get_context",
    # Types
    "Suggestion",
    "SuggestionType",
    "TableRef",
    # Constants
    "SQL_KEYWORDS",
    "SQL_FUNCTIONS",
    "SQL_OPERATORS",
    "SQL_DATA_TYPES",
    "SQL_CONSTRAINTS",
    "SQL_TABLE_CONSTRAINTS",
    "ALTER_OPERATIONS",
    "DROP_OBJECTS",
    "RESERVED_WORDS",
    # Utilities
    "fuzzy_match",
    "extract_table_refs",
    "extract_cte_names",
    "get_all_keywords",
    "get_all_functions",
    # Statement-specific - DML
    "get_insert_context",
    "get_update_context",
    "get_delete_context",
    "extract_delete_table_refs",
    # Statement-specific - DDL
    "get_create_table_context",
    "get_create_table_completions",
    "get_alter_table_context",
    "get_alter_table_completions",
    "get_drop_context",
    "get_drop_completions",
    "get_create_index_completions",
    "get_create_view_completions",
    "get_truncate_completions",
    # Helper functions (public)
    "is_inside_string",
    "remove_string_literals",
    "remove_comments",
    "find_context_keyword",
    "find_last_keyword",
    "find_current_clause",
    "get_current_word",
    "build_alias_map",
    # Backwards compatibility (private names)
    "_is_inside_string",
    "_remove_string_literals",
    "_remove_comments",
    "_find_context_keyword",
    "_find_last_keyword",
    "_find_current_clause",
    "_get_current_word",
    "_build_alias_map",
]
