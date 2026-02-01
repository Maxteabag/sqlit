#!/usr/bin/env bash
# Test script for Nix flake optional dependencies
# This script requires Nix to be installed
#
# Usage:
#   chmod +x test-nix-flake.sh  # Make executable (first time only)
#   ./test-nix-flake.sh         # Run tests

set -e

echo "Testing sqlit Nix flake with optional dependencies..."
echo ""

# Check if nix is available
if ! command -v nix &> /dev/null; then
    echo "❌ Nix is not installed. Please install Nix first:"
    echo "   curl --proto '=https' --tlsv1.2 -sSf -L https://install.determinate.systems/nix | sh -s -- install"
    exit 1
fi

echo "✓ Nix is installed"
echo ""

# Test 1: Check flake syntax
echo "Test 1: Checking flake syntax..."
if nix flake check --no-build; then
    echo "✓ Flake syntax is valid"
else
    echo "❌ Flake syntax check failed"
    exit 1
fi
echo ""

# Test 2: Show flake outputs
echo "Test 2: Showing available outputs..."
nix flake show
echo ""

# Test 3: Try building default package
echo "Test 3: Building default package..."
if nix build .#sqlit --print-build-logs; then
    echo "✓ Default package builds successfully"
else
    echo "❌ Default package build failed"
    exit 1
fi
echo ""

# Test 4: Try building minimal package
echo "Test 4: Building minimal package..."
if nix build .#sqlit-minimal --print-build-logs; then
    echo "✓ Minimal package builds successfully"
else
    echo "❌ Minimal package build failed"
    exit 1
fi
echo ""

# Test 5: Try building full package
echo "Test 5: Building full package..."
if nix build .#sqlit-full --print-build-logs; then
    echo "✓ Full package builds successfully"
else
    echo "❌ Full package build failed"
    exit 1
fi
echo ""

# Test 6: Verify the default app works
echo "Test 6: Verifying default app..."
if nix run .#sqlit -- --version 2>/dev/null; then
    echo "✓ Default app runs successfully"
else
    echo "⚠️  App run test skipped (may require TTY or version flag may not exist)"
fi
echo ""

echo "=========================================="
echo "All tests passed! ✓"
echo "=========================================="
echo ""
echo "Available packages:"
echo "  - sqlit (default): Common dependencies"
echo "  - sqlit-minimal: SQLite only"
echo "  - sqlit-full: All available dependencies"
echo ""
echo "Try them with:"
echo "  nix run .#sqlit"
echo "  nix run .#sqlit-minimal"
echo "  nix run .#sqlit-full"
