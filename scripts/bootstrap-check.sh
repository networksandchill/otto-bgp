#!/bin/bash
#
# Otto BGP Bootstrap Checker
# 
# Verifies installation prerequisites and virtual environment
# Used by installers to fail fast with clear messages
#
# Usage:
#   ./scripts/bootstrap-check.sh [venv_path]
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
VENV_PATH="${1:-venv}"
REQUIRED_PYTHON_VERSION="3.9"

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

# Check Python version
check_python_version() {
    log_info "Checking Python version..."
    
    if ! command -v python3 >/dev/null 2>&1; then
        log_error "Python 3 not found"
        echo "Install Python 3.9+ and retry"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    PYTHON_VERSION_NUM=$(echo "$PYTHON_VERSION" | sed 's/\.//')
    REQUIRED_VERSION_NUM=$(echo "$REQUIRED_PYTHON_VERSION" | sed 's/\.//')
    
    if [[ "$PYTHON_VERSION_NUM" -lt "$REQUIRED_VERSION_NUM" ]]; then
        log_error "Python $PYTHON_VERSION found, but $REQUIRED_PYTHON_VERSION+ required"
        echo "Upgrade Python and retry"
        exit 1
    fi
    
    log_success "Python $PYTHON_VERSION found"
}

# Check virtual environment exists
check_venv_exists() {
    log_info "Checking virtual environment..."
    
    if [[ ! -d "$VENV_PATH" ]]; then
        log_error "Virtual environment not found at $VENV_PATH"
        echo "Create virtual environment first:"
        echo "  python3 -m venv $VENV_PATH"
        exit 1
    fi
    
    if [[ ! -f "$VENV_PATH/bin/python" ]]; then
        log_error "Virtual environment Python not found at $VENV_PATH/bin/python"
        echo "Recreate virtual environment:"
        echo "  rm -rf $VENV_PATH && python3 -m venv $VENV_PATH"
        exit 1
    fi
    
    log_success "Virtual environment found at $VENV_PATH"
}

# Check virtual environment is clean and has required packages
check_venv_imports() {
    log_info "Checking virtual environment imports..."
    
    VENV_PYTHON="$VENV_PATH/bin/python"
    
    # Test basic Python functionality
    if ! "$VENV_PYTHON" -c "import sys; print('Python', sys.version)" >/dev/null 2>&1; then
        log_error "Virtual environment Python is not working"
        echo "Recreate virtual environment:"
        echo "  rm -rf $VENV_PATH && python3 -m venv $VENV_PATH"
        exit 1
    fi
    
    # Test required imports
    local failed_imports=()
    
    for package in yaml paramiko; do
        if ! "$VENV_PYTHON" -c "import $package" >/dev/null 2>&1; then
            failed_imports+=("$package")
        fi
    done
    
    if [[ ${#failed_imports[@]} -gt 0 ]]; then
        log_error "Missing required packages: ${failed_imports[*]}"
        echo "Install missing packages:"
        echo "  $VENV_PYTHON -m pip install ${failed_imports[*]}"
        exit 1
    fi
    
    log_success "All required packages available"
}

# Check virtual environment Python version
check_venv_python_version() {
    log_info "Checking virtual environment Python version..."
    
    VENV_PYTHON="$VENV_PATH/bin/python"
    VENV_PYTHON_VERSION=$("$VENV_PYTHON" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    VENV_VERSION_NUM=$(echo "$VENV_PYTHON_VERSION" | sed 's/\.//')
    REQUIRED_VERSION_NUM=$(echo "$REQUIRED_PYTHON_VERSION" | sed 's/\.//')
    
    if [[ "$VENV_VERSION_NUM" -lt "$REQUIRED_VERSION_NUM" ]]; then
        log_error "Virtual environment Python $VENV_PYTHON_VERSION found, but $REQUIRED_PYTHON_VERSION+ required"
        echo "Recreate virtual environment with newer Python:"
        echo "  rm -rf $VENV_PATH && python3 -m venv $VENV_PATH"
        exit 1
    fi
    
    log_success "Virtual environment Python $VENV_PYTHON_VERSION is compatible"
}

# Main bootstrap check
main() {
    echo "Otto BGP Bootstrap Checker"
    echo "========================="
    echo ""
    
    check_python_version
    check_venv_exists
    check_venv_python_version
    check_venv_imports
    
    echo ""
    log_success "Bootstrap check passed - Otto BGP ready to run"
    echo ""
    echo "Quick start:"
    echo "  $VENV_PATH/bin/python -m otto_bgp.main --help"
}

# Run bootstrap check
main "$@"