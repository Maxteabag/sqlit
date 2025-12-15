from .base import ColumnInfo, DatabaseAdapter, TableInfo
from .cockroachdb import CockroachDBAdapter
from .duckdb import DuckDBAdapter
from .mariadb import MariaDBAdapter
from .mssql import SQLServerAdapter
from .mysql import MySQLAdapter
from .oracle import OracleAdapter
from .postgresql import PostgreSQLAdapter
from .sqlite import SQLiteAdapter
from .supabase import SupabaseAdapter
from .turso import TursoAdapter

__all__ = [
    "ColumnInfo",
    "DatabaseAdapter",
    "TableInfo",
    "CockroachDBAdapter",
    "DuckDBAdapter",
    "MariaDBAdapter",
    "MySQLAdapter",
    "OracleAdapter",
    "PostgreSQLAdapter",
    "SQLiteAdapter",
    "SQLServerAdapter",
    "SupabaseAdapter",
    "TursoAdapter",
    "get_adapter",
]


def get_adapter(db_type: str) -> DatabaseAdapter:
    adapters = {
        "mssql": SQLServerAdapter(),
        "sqlite": SQLiteAdapter(),
        "postgresql": PostgreSQLAdapter(),
        "mysql": MySQLAdapter(),
        "oracle": OracleAdapter(),
        "mariadb": MariaDBAdapter(),
        "duckdb": DuckDBAdapter(),
        "cockroachdb": CockroachDBAdapter(),
        "turso": TursoAdapter(),
        "supabase": SupabaseAdapter(),
    }
    adapter = adapters.get(db_type)
    if not adapter:
        raise ValueError(f"Unknown database type: {db_type}")
    return adapter
