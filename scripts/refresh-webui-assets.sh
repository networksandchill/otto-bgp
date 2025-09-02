#!/bin/bash
#
# refresh-webui-assets.sh - Refresh WebUI assets from GitHub
# Updates the frontend assets without full reinstallation
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
WEBUI_DIR="/usr/local/share/otto-bgp/webui"
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
if [[ ! -w "$WEBUI_DIR" ]] && [[ $EUID -ne 0 ]]; then
    log_error "This script needs to write to $WEBUI_DIR"
    log_info "Please run with sudo: sudo $0 $@"
    exit 1
fi

# Main execution
main() {
    log_info "Otto BGP WebUI Asset Refresh Tool"
    log_info "===================================="
    echo ""
    
    # Check if WebUI directory exists
    if [[ ! -d "$WEBUI_DIR" ]]; then
        log_error "WebUI directory not found at $WEBUI_DIR"
        log_error "Is Otto BGP WebUI installed?"
        exit 1
    fi
    
    log_info "Fetching latest assets from GitHub (branch: $BRANCH)..."
    
    # Download the static assets from GitHub
    cd "$TEMP_DIR"
    
    # Use sparse checkout to only get webui/static directory
    git clone --depth 1 --branch "$BRANCH" --filter=blob:none --sparse "$GITHUB_REPO" otto-temp 2>/dev/null || {
        log_error "Failed to clone repository. Check your internet connection and branch name."
        exit 1
    }
    
    cd otto-temp
    git sparse-checkout set webui/static
    
    # Check if assets exist
    if [[ ! -d "webui/static" ]]; then
        log_error "No webui/static directory found in repository"
        exit 1
    fi
    
    # Check if there are actual changes
    if [[ -d "$WEBUI_DIR/assets" ]]; then
        # Get hash of current assets
        CURRENT_HASH=$(find "$WEBUI_DIR" -type f -exec md5sum {} \; 2>/dev/null | sort | md5sum | cut -d' ' -f1)
        NEW_HASH=$(find "webui/static" -type f -exec md5sum {} \; 2>/dev/null | sort | md5sum | cut -d' ' -f1)
        
        if [[ "$CURRENT_HASH" == "$NEW_HASH" ]]; then
            log_info "Assets are already up to date!"
            exit 0
        fi
    fi
    
    # Backup current assets
    if [[ -d "$WEBUI_DIR" ]]; then
        BACKUP_DIR="${WEBUI_DIR}.backup.$(date +%Y%m%d-%H%M%S)"
        log_info "Backing up current assets to $BACKUP_DIR"
        
        if [[ $EUID -eq 0 ]]; then
            cp -r "$WEBUI_DIR" "$BACKUP_DIR"
        else
            sudo cp -r "$WEBUI_DIR" "$BACKUP_DIR"
        fi
    fi
    
    # Copy new assets
    log_info "Installing new assets..."
    
    if [[ $EUID -eq 0 ]]; then
        rm -rf "${WEBUI_DIR:?}"/*
        cp -r webui/static/* "$WEBUI_DIR/"
        
        # Set proper permissions
        chown -R otto-bgp:otto-bgp "$WEBUI_DIR" 2>/dev/null || true
        chmod -R 755 "$WEBUI_DIR"
    else
        sudo rm -rf "${WEBUI_DIR:?}"/*
        sudo cp -r webui/static/* "$WEBUI_DIR/"
        
        # Set proper permissions
        sudo chown -R otto-bgp:otto-bgp "$WEBUI_DIR" 2>/dev/null || true
        sudo chmod -R 755 "$WEBUI_DIR"
    fi
    
    # Get the latest commit info
    COMMIT_HASH=$(git rev-parse --short HEAD)
    COMMIT_MSG=$(git log -1 --pretty=format:"%s")
    COMMIT_DATE=$(git log -1 --pretty=format:"%ci")
    
    log_info "Assets updated successfully!"
    echo ""
    echo "Latest commit: $COMMIT_HASH"
    echo "Message: $COMMIT_MSG"
    echo "Date: $COMMIT_DATE"
    echo ""
    
    # Check if service is running and offer to restart
    if systemctl is-active --quiet otto-bgp-webui-adapter.service; then
        log_warn "WebUI service is running"
        
        if [[ -t 0 ]]; then  # Check if running interactively
            read -p "Restart otto-bgp-webui-adapter service now? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                log_info "Restarting WebUI service..."
                if [[ $EUID -eq 0 ]]; then
                    systemctl restart otto-bgp-webui-adapter.service
                else
                    sudo systemctl restart otto-bgp-webui-adapter.service
                fi
                log_info "Service restarted"
            else
                log_info "Service not restarted. Restart manually with:"
                echo "  sudo systemctl restart otto-bgp-webui-adapter.service"
            fi
        else
            log_info "To apply changes, restart the service:"
            echo "  sudo systemctl restart otto-bgp-webui-adapter.service"
        fi
    fi
    
    log_info "Done!"
}

# Show usage
if [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
    echo "Usage: $0 [branch]"
    echo ""
    echo "Refresh Otto BGP WebUI assets from GitHub repository"
    echo ""
    echo "Arguments:"
    echo "  branch    Git branch to pull from (default: main)"
    echo ""
    echo "Examples:"
    echo "  $0              # Pull from main branch"
    echo "  $0 webui        # Pull from webui branch"
    echo "  $0 develop      # Pull from develop branch"
    echo ""
    echo "Note: Requires sudo if not running as root"
    exit 0
fi

# Run main function
main