#!/bin/bash
# Run Athena integration tests with ephemeral Terraform infrastructure
#
# Usage:
#   ./tests/athena/run_tests.sh [pytest args...]
#
# Examples:
#   ./tests/athena/run_tests.sh                    # Run all Athena tests
#   ./tests/athena/run_tests.sh -v                 # Verbose output
#   ./tests/athena/run_tests.sh -k "test_connect"  # Run specific test
#
# Environment variables:
#   AWS_REGION    - AWS region (default: us-east-1)
#   SKIP_DESTROY  - Set to 1 to keep infrastructure after tests (for debugging)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TF_DIR="$SCRIPT_DIR/infra"
VENV_DIR="$PROJECT_ROOT/.venv"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Track if we created infrastructure (for cleanup)
INFRA_CREATED=false

# Cleanup function - always runs on exit
cleanup() {
    local exit_code=$?

    if [[ "$INFRA_CREATED" != "true" ]]; then
        exit $exit_code
    fi

    if [[ "${SKIP_DESTROY:-0}" == "1" ]]; then
        log_warn "SKIP_DESTROY is set - infrastructure will NOT be destroyed"
        log_warn "Remember to run: cd $TF_DIR && terraform destroy"
        exit $exit_code
    fi

    echo ""
    log_info "Cleaning up Terraform infrastructure..."
    cd "$TF_DIR"

    if terraform destroy -auto-approve > /dev/null 2>&1; then
        log_success "Infrastructure destroyed"
    else
        log_error "Failed to destroy infrastructure. Manual cleanup may be required."
        log_error "Run: cd $TF_DIR && terraform destroy"
    fi

    exit $exit_code
}

# Set trap for cleanup
trap cleanup EXIT INT TERM

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check terraform
    if ! command -v terraform &> /dev/null; then
        log_error "Terraform not found. Install from: https://terraform.io/downloads"
        exit 1
    fi
    log_success "Terraform found"

    # Check AWS credentials
    if [[ ! -f ~/.aws/credentials ]] && [[ -z "$AWS_ACCESS_KEY_ID" ]]; then
        log_error "AWS credentials not configured"
        log_error "Run: mkdir -p ~/.aws && edit ~/.aws/credentials"
        exit 1
    fi
    log_success "AWS credentials found"

    # Check venv
    if [[ ! -d "$VENV_DIR" ]]; then
        log_error "Virtual environment not found at $VENV_DIR"
        exit 1
    fi
    log_success "Virtual environment found"

    # Check pyathena in venv
    if ! "$VENV_DIR/bin/python" -c "import pyathena" 2>/dev/null; then
        log_warn "pyathena not installed in venv, installing..."
        "$VENV_DIR/bin/pip" install pyathena > /dev/null
    fi
    log_success "pyathena available"

    # Check boto3 for system python (needed by Terraform)
    if ! python3 -c "import boto3" 2>/dev/null; then
        log_error "boto3 not installed for system python3 (needed by Terraform)"
        log_error "Run: pip3 install boto3 --break-system-packages"
        exit 1
    fi
    log_success "boto3 available for Terraform"
}

# Initialize and apply Terraform
setup_infrastructure() {
    log_info "Setting up Athena test infrastructure..."
    cd "$TF_DIR"

    # Initialize Terraform
    log_info "Initializing Terraform..."
    if ! terraform init -input=false > /dev/null 2>&1; then
        log_error "Terraform init failed"
        exit 1
    fi

    # Apply
    log_info "Applying Terraform configuration (this may take ~30 seconds)..."
    if ! terraform apply -auto-approve -input=false; then
        log_error "Terraform apply failed"
        exit 1
    fi

    INFRA_CREATED=true

    # Extract outputs
    ATHENA_BUCKET=$(terraform output -raw bucket_name)
    ATHENA_DATABASE=$(terraform output -raw database_name)
    ATHENA_WORKGROUP=$(terraform output -raw workgroup)
    ATHENA_S3_STAGING_DIR=$(terraform output -raw s3_staging_dir)
    AWS_REGION=$(terraform output -raw aws_region)

    export ATHENA_BUCKET
    export ATHENA_DATABASE
    export ATHENA_WORKGROUP
    export ATHENA_S3_STAGING_DIR
    export ATHENA_USE_TERRAFORM=1
    export AWS_REGION

    echo ""
    log_success "Infrastructure ready:"
    echo "  Bucket:      $ATHENA_BUCKET"
    echo "  Database:    $ATHENA_DATABASE"
    echo "  Workgroup:   $ATHENA_WORKGROUP"
    echo "  Region:      $AWS_REGION"
}

# Run pytest
run_tests() {
    echo ""
    log_info "Running Athena integration tests..."
    cd "$PROJECT_ROOT"

    # Activate venv and run tests
    source "$VENV_DIR/bin/activate"

    local pytest_args=("tests/athena/test_athena.py" "$@")

    echo ""
    if pytest "${pytest_args[@]}"; then
        echo ""
        log_success "All tests passed!"
        return 0
    else
        echo ""
        log_error "Some tests failed"
        return 1
    fi
}

# Main
main() {
    echo ""
    echo "========================================"
    echo "  Athena Integration Test Runner"
    echo "========================================"
    echo ""

    check_prerequisites
    echo ""
    setup_infrastructure
    run_tests "$@"
}

main "$@"
