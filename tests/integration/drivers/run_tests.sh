#!/bin/bash
set -e

cd "$(dirname "$0")"

start_mssql() {
    echo "Starting SQL Server..."
    docker-compose up -d mssql

    echo "Waiting for SQL Server to be healthy..."
    timeout=120
    while [ $timeout -gt 0 ]; do
        if docker-compose ps mssql | grep -q "healthy"; then
            return 0
        fi
        echo "  Waiting... ($timeout seconds remaining)"
        sleep 5
        timeout=$((timeout - 5))
    done

    echo "ERROR: SQL Server failed to start"
    docker-compose logs mssql
    exit 1
}

case "${1:-all}" in
    --clean)
        docker-compose down -v --rmi local 2>/dev/null || true
        ;;
    all)
        start_mssql
        docker-compose up --build \
            test-ubuntu \
            test-debian \
            test-rocky \
            test-fedora \
            test-alpine \
            test-opensuse \
            test-arch
        ;;
    ubuntu|debian|rocky|fedora|alpine|opensuse|arch)
        start_mssql
        docker-compose up --build "test-$1"
        ;;
    *)
        echo "Usage: $0 [all|ubuntu|debian|rocky|fedora|alpine|opensuse|arch|--clean]"
        exit 1
        ;;
esac
