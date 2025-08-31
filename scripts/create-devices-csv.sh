#!/bin/bash

# Script to create a basic devices.csv file for Otto BGP
# This is useful when the WebUI setup didn't create it or you need to recreate it

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

DEVICES_CSV="/etc/otto-bgp/devices.csv"

echo -e "${GREEN}Otto BGP Devices CSV Creator${NC}"
echo "============================"
echo ""

# Check if running as root for system installation
if [[ -w "/etc/otto-bgp" ]]; then
    echo "Creating system-wide devices.csv at $DEVICES_CSV"
else
    # User installation
    DEVICES_CSV="$HOME/.config/otto-bgp/devices.csv"
    echo "Creating user devices.csv at $DEVICES_CSV"
    mkdir -p "$(dirname "$DEVICES_CSV")"
fi

# Check if file exists
if [[ -f "$DEVICES_CSV" ]]; then
    echo -e "${YELLOW}Warning: $DEVICES_CSV already exists${NC}"
    read -p "Do you want to overwrite it? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# Collect device information
echo ""
echo "Enter device information (press Enter for defaults):"
echo ""

read -p "Device IP/Hostname [192.168.1.1]: " DEVICE_ADDRESS
DEVICE_ADDRESS=${DEVICE_ADDRESS:-192.168.1.1}

# Auto-generate hostname if IP address is provided
if [[ "$DEVICE_ADDRESS" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    DEFAULT_HOSTNAME="router-$(echo "$DEVICE_ADDRESS" | tr '.' '-')"
else
    DEFAULT_HOSTNAME="$DEVICE_ADDRESS"
fi

read -p "Device Name [$DEFAULT_HOSTNAME]: " DEVICE_HOSTNAME
DEVICE_HOSTNAME=${DEVICE_HOSTNAME:-$DEFAULT_HOSTNAME}

read -p "SSH Username [admin]: " SSH_USERNAME
SSH_USERNAME=${SSH_USERNAME:-admin}

read -p "Device Role (edge/core/transit/lab) [edge]: " DEVICE_ROLE
DEVICE_ROLE=${DEVICE_ROLE:-edge}

read -p "Region [default]: " DEVICE_REGION
DEVICE_REGION=${DEVICE_REGION:-default}

# Create the CSV file
echo ""
echo "Creating devices.csv..."

cat > "$DEVICES_CSV" << EOF
address,hostname,username,role,region
$DEVICE_ADDRESS,$DEVICE_HOSTNAME,$SSH_USERNAME,$DEVICE_ROLE,$DEVICE_REGION
EOF

# Set appropriate permissions
chmod 644 "$DEVICES_CSV"

echo -e "${GREEN}✓ Successfully created $DEVICES_CSV${NC}"
echo ""
echo "Contents:"
cat "$DEVICES_CSV"
echo ""

# Additional instructions
echo "To add more devices, edit the file directly:"
echo "  nano $DEVICES_CSV"
echo ""
echo "Example additional entries:"
echo "  192.168.1.2,edge-router-02,admin,edge,us-east"
echo "  192.168.2.1,core-router-01,admin,core,us-west"
echo ""

# Test if otto-bgp service can now start
if systemctl is-active --quiet otto-bgp.service 2>/dev/null; then
    echo -e "${GREEN}✓ Otto BGP service is already running${NC}"
elif systemctl is-enabled --quiet otto-bgp.service 2>/dev/null; then
    echo "You can now start the Otto BGP service:"
    echo "  sudo systemctl start otto-bgp.service"
fi