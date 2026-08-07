"""Example usage of IBM DB2 for i adapter.

This example demonstrates how to connect to IBM DB2 for i using the ODBC driver.
"""

from sqlit.domains.connections.domain.config import ConnectionConfig, TcpEndpoint
from sqlit.domains.connections.providers.catalog import get_provider


def example_connection():
    """Example of creating a DB2 for i connection."""
    
    # Create a connection configuration
    config = ConnectionConfig(
        name="my_ibm_i_server",
        db_type="db2i",
        tcp_endpoint=TcpEndpoint(
            host="your.ibmi.server.com",
            port=None,  # Port is optional for IBM i Access ODBC Driver
            database="MYLIB",  # Default library/schema
            username="your_username",
            password="your_password",
        ),
        extra_options={
            # Optional: specify custom ODBC driver name if different from default
            # "odbc_driver": "IBM i Access ODBC Driver",
            
            # Optional: additional ODBC connection string options
            # "CHARSET": "UTF-8",
            # "NAM": "1",  # Naming convention: 1=SQL, 0=System
        },
    )
    
    # Get the provider
    provider = get_provider("db2i")
    
    # Create a connection
    conn = provider.connection_factory.connect(config)
    
    # Example: Get list of libraries
    libraries = provider.schema_inspector.get_databases(conn)
    print(f"Available libraries: {libraries}")
    
    # Example: Get tables from a library
    tables = provider.schema_inspector.get_tables(conn, database="MYLIB")
    print(f"Tables in MYLIB: {[t[1] for t in tables]}")
    
    # Example: Execute a query
    columns, rows, truncated = provider.query_executor.execute_query(
        conn, 
        "SELECT * FROM MYLIB.MYTABLE",
        max_rows=100
    )
    print(f"Query returned {len(rows)} rows")
    print(f"Columns: {columns}")
    
    # Close connection
    conn.close()


def example_url_connection():
    """Example of using a URL-style connection string."""
    
    # URL format: db2i://username:password@hostname/library
    url = "db2i://myuser:mypass@ibmi.example.com/MYLIB"
    
    # You can parse this URL and create a ConnectionConfig
    # (URL parsing functionality would be in the main sqlit application)
    print(f"Connection URL: {url}")


if __name__ == "__main__":
    print("IBM DB2 for i Connection Examples")
    print("=" * 50)
    print()
    print("To use these examples, you need:")
    print("1. IBM i Access ODBC Driver installed on your system")
    print("2. pyodbc Python package: pip install pyodbc")
    print("3. Network access to your IBM i server")
    print()
    print("Uncomment example_connection() to test")
    # example_connection()
