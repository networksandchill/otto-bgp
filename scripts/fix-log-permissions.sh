#!/bin/bash

# Fix log permissions for otto-bgp user
# This adds the otto-bgp user to the appropriate group for reading journalctl logs

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Otto BGP Log Permission Fix${NC}"
echo "============================"
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root (use sudo)${NC}"
   exit 1
fi

SERVICE_USER="otto-bgp"

# Check if user exists
if ! id "$SERVICE_USER" &>/dev/null; then
    echo -e "${RED}User $SERVICE_USER does not exist${NC}"
    exit 1
fi

echo "Current groups for $SERVICE_USER:"
groups "$SERVICE_USER"
echo ""

# Add to systemd-journal group if it exists
if getent group systemd-journal >/dev/null 2>&1; then
    echo "Adding $SERVICE_USER to systemd-journal group..."
    usermod -a -G systemd-journal "$SERVICE_USER"
    echo -e "${GREEN}✓ Added to systemd-journal group${NC}"
elif getent group adm >/dev/null 2>&1; then
    echo "Adding $SERVICE_USER to adm group..."
    usermod -a -G adm "$SERVICE_USER"
    echo -e "${GREEN}✓ Added to adm group${NC}"
else
    echo -e "${YELLOW}Warning: Neither systemd-journal nor adm group found${NC}"
    echo "You may need to manually configure log access"
fi

# Restart the WebUI service to apply group changes
if systemctl is-active --quiet otto-bgp-webui-adapter.service; then
    echo ""
    echo "Restarting WebUI service to apply group changes..."
    systemctl restart otto-bgp-webui-adapter.service
    echo -e "${GREEN}✓ WebUI service restarted${NC}"
fi

echo ""
echo "New groups for $SERVICE_USER:"
groups "$SERVICE_USER"
echo ""
echo -e "${GREEN}Log permissions fixed!${NC}"
echo ""
echo "The WebUI logs page should now be able to display system logs."