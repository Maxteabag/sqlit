#!/usr/bin/env python3
"""Test script to verify DB2i adapter is working."""

import sys
sys.path.insert(0, '.')

from sqlit.domains.connections.providers.db2i.adapter import Db2iAdapter
from sqlit.domains.connections.providers.catalog import get_supported_db_types, get_provider

def test_adapter():
    """Test the DB2i adapter directly."""
    print("Testing DB2i Adapter...")
    adapter = Db2iAdapter()
    print(f"✓ Adapter name: {adapter.name}")
    print(f"✓ Install package: {adapter.install_package}")
    print(f"✓ Install extra: {adapter.install_extra}")
    print(f"✓ Driver imports: {adapter.driver_import_names}")
    print(f"✓ Supports multiple databases: {adapter.supports_multiple_databases}")
    print(f"✓ Supports stored procedures: {adapter.supports_stored_procedures}")
    print(f"✓ Supports sequences: {adapter.supports_sequences}")
    print()

def test_provider_registration():
    """Test that the provider is properly registered."""
    print("Testing Provider Registration...")
    db_types = get_supported_db_types()
    
    if 'db2i' in db_types:
        print("✓ DB2i provider is registered")
        provider = get_provider('db2i')
        print(f"✓ Provider display name: {provider.metadata.display_name}")
        print(f"✓ Provider URL schemes: {provider.metadata.url_schemes}")
        print(f"✓ Provider badge: {provider.metadata.badge_label}")
    else:
        print("✗ DB2i provider is NOT registered")
        print(f"Available types: {sorted(db_types)}")
    print()

if __name__ == '__main__':
    test_adapter()
    test_provider_registration()
    print("All tests completed!")
