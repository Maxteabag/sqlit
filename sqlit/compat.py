"""Compatibility checks for optional dependencies."""

import importlib.util

PYODBC_AVAILABLE = importlib.util.find_spec("pyodbc") is not None
