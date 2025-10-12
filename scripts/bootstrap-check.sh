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
# Determine default venv path to match installer locations:
# - User mode:   $HOME/.local/venv
# - System mode: /usr/local/venv
if [[ -n "${1:-}" ]]; then
    VENV_PATH="$1"
else
    if [[ "$(id -u)" -eq 0 ]]; then
        VENV_PATH="/usr/local/venv"
    else
        VENV_PATH="$HOME/.local/venv"
    fi
fi
REQUIRED_PYTHON_VERSION="3.12"
PYTHON_BIN=""  # Will be populated when probing system Python

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
# Probe system Python and require 3.12+ (prefer 3.13 → 3.12 → python3)
check_python_version() {
    log_info "Checking system Python for venv creation..."

    local candidates=(python3.13 python3.12 python3)
    local found=""
    local ver="0.0"

    for cmd in "${candidates[@]}"; do
        if command -v "$cmd" >/dev/null 2>&1; then
            ver=$("$cmd" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))' 2>/dev/null || echo "0.0")
            if [[ "${ver//.}" -ge 312 ]]; then
                found="$cmd"
                break
            fi
        fi
    done

    if [[ -z "$found" ]]; then
        log_error "Python 3.12+ required but not found"
        echo "Install Python 3.12+ and retry"
        exit 1
    fi

    PYTHON_BIN=$(command -v "$found")
    log_success "Using $ver ($PYTHON_BIN) for venv creation guidance"
}

# Check virtual environment exists
check_venv_exists() {
    log_info "Checking virtual environment..."
    
    if [[ ! -d "$VENV_PATH" ]]; then
        log_error "Virtual environment not found at $VENV_PATH"
        echo "Create virtual environment first:"
        if [[ -n "$PYTHON_BIN" ]]; then
            echo "  $PYTHON_BIN -m venv $VENV_PATH"
        else
            echo "  python3 -m venv $VENV_PATH"
        fi
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
    
    # Prefer checking an existing virtual environment; only check system Python
    # when a venv is not present (to guide venv creation).
    if [[ -d "$VENV_PATH" ]]; then
        check_venv_python_version
        check_venv_imports
    else
        check_python_version
        check_venv_exists  # Will exit with guidance
    fi
    
    echo ""
    log_success "Bootstrap check passed - Otto BGP ready to run"
    echo ""
    echo "Quick start:"
    echo "  $VENV_PATH/bin/python -m otto_bgp.main --help"
}

# Run bootstrap check
main "$@"
