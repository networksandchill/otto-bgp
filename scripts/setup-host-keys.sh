#!/bin/bash
#
# Otto BGP - SSH Host Key Setup Script
#
# This script collects SSH host keys from all network devices stored in the
# Otto BGP database (router_inventory table). This is a one-time setup step
# that must be run before production deployment to enable secure host key verification.
#
# Security Note: This script should be run from a trusted network where you
# can verify the authenticity of the network devices. After collection, the
# host keys should be reviewed before production use.
#
# Usage:
#   ./setup-host-keys.sh [known_hosts_output]
#
# Environment Variables:
#   OTTO_DB_PATH - Path to Otto database (default: /var/lib/otto-bgp/otto.db)
#
# Defaults:
#   known_hosts: /var/lib/otto-bgp/ssh-keys/known_hosts
#

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default paths
DEFAULT_KNOWN_HOSTS="/var/lib/otto-bgp/ssh-keys/known_hosts"

# Use provided path or default
KNOWN_HOSTS="${1:-$DEFAULT_KNOWN_HOSTS}"

# Database path (configurable via environment variable)
DB_PATH="${OTTO_DB_PATH:-/var/lib/otto-bgp/otto.db}"

# Verify user
EXPECTED_USER="otto.bgp"
if [[ "$USER" != "$EXPECTED_USER" ]] && [[ "$USER" != "root" ]]; then
    echo -e "${YELLOW}Warning: This script should be run as $EXPECTED_USER or root${NC}"
    echo "Current user: $USER"
fi

# Function to print colored messages
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Header
echo "========================================"
echo "Otto BGP SSH Host Key Collection"
echo "========================================"
echo

# Check prerequisites
if ! command -v sqlite3 &> /dev/null; then
    log_error "sqlite3 is required but not installed"
    exit 1
fi

if ! command -v ssh-keyscan &> /dev/null; then
    log_error "ssh-keyscan is required but not installed"
    exit 1
fi

# Check if database exists
if [[ ! -f "$DB_PATH" ]]; then
    log_error "Database not found: $DB_PATH"
    echo "Please ensure Otto BGP is installed and the database is initialized"
    exit 1
fi

# Check if router_inventory table has data
ROUTER_COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM router_inventory;" 2>/dev/null || echo "0")

if [[ "$ROUTER_COUNT" -eq 0 ]]; then
    log_error "No routers found in database"
    echo "Please add routers to the inventory before collecting host keys"
    echo "Use: otto-bgp discover or add routers manually"
    exit 1
fi

log_info "Found $ROUTER_COUNT routers in database"

# Create SSH keys directory if it doesn't exist
KNOWN_HOSTS_DIR=$(dirname "$KNOWN_HOSTS")
if [[ ! -d "$KNOWN_HOSTS_DIR" ]]; then
    log_info "Creating SSH keys directory: $KNOWN_HOSTS_DIR"
    mkdir -p "$KNOWN_HOSTS_DIR"

    # Set proper ownership if running as root
    if [[ "$USER" == "root" ]] && id -u otto.bgp >/dev/null 2>&1; then
        chown otto.bgp:otto.bgp "$KNOWN_HOSTS_DIR"
    fi
fi

# Backup existing known_hosts if it exists
if [[ -f "$KNOWN_HOSTS" ]]; then
    BACKUP_FILE="${KNOWN_HOSTS}.backup.$(date +%Y%m%d_%H%M%S)"
    log_warn "Existing known_hosts found. Creating backup: $BACKUP_FILE"
    cp "$KNOWN_HOSTS" "$BACKUP_FILE"
fi

# Initialize known_hosts file
> "$KNOWN_HOSTS"
log_info "Collecting SSH host keys from routers..."
echo

# Statistics
TOTAL_DEVICES=0
SUCCESSFUL_DEVICES=0
FAILED_DEVICES=0
FAILED_LIST=""

# Function to scan a single device
scan_device() {
    local address="$1"
    local hostname="$2"

    # Skip empty addresses
    if [[ -z "$address" ]]; then
        return
    fi

    ((TOTAL_DEVICES++))

    # Display progress
    echo -n "Scanning $hostname ($address)... "

    # Collect SSH host keys (both ed25519 and rsa)
    # Using timeout to prevent hanging on unreachable devices
    if timeout 10 ssh-keyscan -t ed25519,rsa -H "$address" >> "$KNOWN_HOSTS" 2>/dev/null; then
        echo -e "${GREEN}✓${NC}"
        ((SUCCESSFUL_DEVICES++))

        # Also add by hostname if provided and different from address
        if [[ -n "$hostname" ]] && [[ "$hostname" != "$address" ]]; then
            timeout 10 ssh-keyscan -t ed25519,rsa -H "$hostname" >> "$KNOWN_HOSTS" 2>/dev/null
        fi
    else
        echo -e "${RED}✗${NC}"
        ((FAILED_DEVICES++))
        FAILED_LIST="${FAILED_LIST}  - $hostname ($address)\n"
        log_warn "Failed to collect host key from $address"
    fi
}

# Read routers from database
log_info "Reading routers from database..."

# Query database for all routers
sqlite3 "$DB_PATH" "SELECT ip_address, hostname FROM router_inventory ORDER BY hostname;" 2>/dev/null | while IFS='|' read -r address hostname; do
    scan_device "$address" "$hostname"
done

echo
echo "========================================"
echo "Host Key Collection Summary"
echo "========================================"
echo

# Display statistics
log_info "Total devices processed: $TOTAL_DEVICES"
log_info "Successful collections: $SUCCESSFUL_DEVICES"

if [[ $FAILED_DEVICES -gt 0 ]]; then
    log_warn "Failed collections: $FAILED_DEVICES"
    echo -e "${YELLOW}Failed devices:${NC}"
    echo -e "$FAILED_LIST"
fi

# Count unique host keys collected
if [[ -f "$KNOWN_HOSTS" ]]; then
    KEY_COUNT=$(wc -l < "$KNOWN_HOSTS")
    log_info "Total host keys collected: $KEY_COUNT"
fi

# Set proper permissions
if [[ -f "$KNOWN_HOSTS" ]]; then
    chmod 644 "$KNOWN_HOSTS"

    # Set proper ownership if running as root
    if [[ "$USER" == "root" ]] && id -u otto.bgp >/dev/null 2>&1; then
        chown otto.bgp:otto.bgp "$KNOWN_HOSTS"
        log_info "Set ownership to otto.bgp:otto.bgp"
    fi

    log_info "Host keys saved to: $KNOWN_HOSTS"
fi

echo
echo "========================================"
echo "Next Steps"
echo "========================================"
echo
echo "1. Review the collected host keys:"
echo "   ssh-keygen -l -f $KNOWN_HOSTS"
echo
echo "2. Verify host key fingerprints with your network team"
echo
echo "3. Test SSH connections with strict host checking:"
echo "   ssh -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$KNOWN_HOSTS user@device"
echo

if [[ $FAILED_DEVICES -gt 0 ]]; then
    echo -e "${YELLOW}Warning: Some devices failed. You may need to:${NC}"
    echo "  - Check network connectivity to failed devices"
    echo "  - Verify SSH is enabled on those devices"
    echo "  - Manually add their host keys using ssh-keyscan"
    echo
fi

echo "Security reminder: These host keys protect against MITM attacks."
echo "Store this file securely and track any changes."

exit 0