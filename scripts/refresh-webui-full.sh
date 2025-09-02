#!/bin/bash
#
# refresh-webui-full.sh - Refresh WebUI backend AND frontend from GitHub
# Updates both Python backend and frontend assets without full reinstallation
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
GITHUB_REPO="https://github.com/networksandchill/otto-bgp"
BRANCH="${1:-main}"  # Default to main, allow override
WEBUI_ASSETS_DIR="/usr/local/share/otto-bgp/webui"
WEBUI_BACKEND_DIR="/usr/local/lib/otto-bgp/webui"
TEMP_DIR=$(mktemp -d)

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

cleanup() {
    rm -rf "$TEMP_DIR"
}

# Set trap for cleanup
trap cleanup EXIT

# Check if running with appropriate permissions
if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root"
    log_info "Please run: sudo $0 $@"
    exit 1
fi

# Main execution
main() {
    log_info "Otto BGP WebUI Full Refresh Tool"
    log_info "===================================="
    echo ""
    
    # Check if WebUI directories exist
    if [[ ! -d "$WEBUI_ASSETS_DIR" ]] || [[ ! -d "$WEBUI_BACKEND_DIR" ]]; then
        log_error "WebUI directories not found"
        log_error "Assets: $WEBUI_ASSETS_DIR"
        log_error "Backend: $WEBUI_BACKEND_DIR"
        log_error "Is Otto BGP WebUI installed?"
        exit 1
    fi
    
    log_info "Fetching latest code from GitHub (branch: $BRANCH)..."
    
    # Download from GitHub
    cd "$TEMP_DIR"
    
    # Use sparse checkout to only get webui directories
    git clone --depth 1 --branch "$BRANCH" --filter=blob:none --sparse "$GITHUB_REPO" otto-temp 2>/dev/null || {
        log_error "Failed to clone repository. Check your internet connection and branch name."
        exit 1
    }
    
    cd otto-temp
    git sparse-checkout set webui
    
    # Check if directories exist
    if [[ ! -d "webui" ]]; then
        log_error "No webui directory found in repository"
        exit 1
    fi
    
    # Backup current installation
    BACKUP_SUFFIX=".backup.$(date +%Y%m%d-%H%M%S)"
    log_info "Backing up current installation..."
    
    # Backup frontend assets
    if [[ -d "$WEBUI_ASSETS_DIR" ]]; then
        cp -r "$WEBUI_ASSETS_DIR" "${WEBUI_ASSETS_DIR}${BACKUP_SUFFIX}"
    fi
    
    # Update backend Python files
    log_info "Updating backend Python code..."
    
    # Copy root Python files
    for py_file in webui/*.py; do
        if [[ -f "$py_file" ]]; then
            filename=$(basename "$py_file")
            cp "$py_file" "$WEBUI_BACKEND_DIR/$filename"
            log_info "  Updated: $filename"
        fi
    done
    
    # Copy API module directory
    if [[ -d "webui/api" ]]; then
        log_info "  Updating API module..."
        rm -rf "$WEBUI_BACKEND_DIR/api" 2>/dev/null || true
        cp -r "webui/api" "$WEBUI_BACKEND_DIR/"
        log_info "  Updated: api/"
    fi
    
    # Copy Core module directory
    if [[ -d "webui/core" ]]; then
        log_info "  Updating Core module..."
        rm -rf "$WEBUI_BACKEND_DIR/core" 2>/dev/null || true
        cp -r "webui/core" "$WEBUI_BACKEND_DIR/"
        log_info "  Updated: core/"
    fi
    
    # Copy any additional backend files (schemas, settings, etc.)
    for file in webui/*.json webui/*.yaml webui/*.yml; do
        if [[ -f "$file" ]]; then
            filename=$(basename "$file")
            cp "$file" "$WEBUI_BACKEND_DIR/$filename"
            log_info "  Updated: $filename"
        fi
    done
    
    # Update frontend assets
    log_info "Updating frontend assets..."
    
    if [[ -d "webui/static" ]]; then
        rm -rf "${WEBUI_ASSETS_DIR:?}"/*
        cp -r webui/static/* "$WEBUI_ASSETS_DIR/"
        log_info "  Frontend assets updated"
    else
        log_warn "No static assets found in repository"
    fi
    
    # Set proper permissions
    log_info "Setting proper permissions..."
    
    # Backend permissions
    chown -R otto-bgp:otto-bgp "$WEBUI_BACKEND_DIR" 2>/dev/null || true
    chmod -R 755 "$WEBUI_BACKEND_DIR"
    chmod 644 "$WEBUI_BACKEND_DIR"/*.py 2>/dev/null || true
    
    # Frontend permissions
    chown -R otto-bgp:otto-bgp "$WEBUI_ASSETS_DIR" 2>/dev/null || true
    chmod -R 755 "$WEBUI_ASSETS_DIR"
    
    # Get the latest commit info
    COMMIT_HASH=$(git rev-parse --short HEAD)
    COMMIT_MSG=$(git log -1 --pretty=format:"%s")
    COMMIT_DATE=$(git log -1 --pretty=format:"%ci")
    
    log_info "Update completed successfully!"
    echo ""
    echo "Latest commit: $COMMIT_HASH"
    echo "Message: $COMMIT_MSG"
    echo "Date: $COMMIT_DATE"
    echo ""
    
    # Restart service
    if systemctl is-active --quiet otto-bgp-webui-adapter.service; then
        log_info "Restarting WebUI service..."
        systemctl restart otto-bgp-webui-adapter.service
        
        # Wait for service to be ready
        sleep 2
        
        if systemctl is-active --quiet otto-bgp-webui-adapter.service; then
            log_info "Service restarted successfully"
        else
            log_error "Service failed to restart. Check logs with:"
            echo "  journalctl -u otto-bgp-webui-adapter.service -n 50"
            exit 1
        fi
    else
        log_warn "WebUI service is not running"
        log_info "Start it with: systemctl start otto-bgp-webui-adapter.service"
    fi
    
    log_info "Done!"
    
    # Show recent logs
    echo ""
    log_info "Recent service logs:"
    journalctl -u otto-bgp-webui-adapter.service -n 10 --no-pager
}

# Show usage
if [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
    echo "Usage: $0 [branch]"
    echo ""
    echo "Refresh Otto BGP WebUI (backend + frontend) from GitHub repository"
    echo ""
    echo "Arguments:"
    echo "  branch    Git branch to pull from (default: main)"
    echo ""
    echo "Examples:"
    echo "  $0              # Pull from main branch"
    echo "  $0 webui        # Pull from webui branch"
    echo "  $0 develop      # Pull from develop branch"
    echo ""
    echo "Note: Must be run as root (use sudo)"
    exit 0
fi

# Run main function
main