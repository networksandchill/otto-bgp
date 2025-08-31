#!/bin/bash

# Diagnostic script to check otto-bgp user permissions for logs and service control

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}Otto BGP Permission Check${NC}"
echo "=========================="
echo ""

SERVICE_USER="otto-bgp"

# Check if user exists
echo -e "${BLUE}1. Checking user existence:${NC}"
if id "$SERVICE_USER" &>/dev/null; then
    echo -e "${GREEN}✓${NC} User $SERVICE_USER exists"
    echo "  UID: $(id -u $SERVICE_USER)"
    echo "  GID: $(id -g $SERVICE_USER)"
else
    echo -e "${RED}✗${NC} User $SERVICE_USER does not exist"
    exit 1
fi
echo ""

# Check group memberships
echo -e "${BLUE}2. Checking group memberships:${NC}"
GROUPS=$(groups $SERVICE_USER 2>/dev/null | cut -d: -f2)
echo "  Current groups: $GROUPS"

# Check for journal access groups
HAS_JOURNAL_ACCESS=false
if echo "$GROUPS" | grep -q "systemd-journal"; then
    echo -e "${GREEN}✓${NC} Member of systemd-journal group (can read logs)"
    HAS_JOURNAL_ACCESS=true
elif echo "$GROUPS" | grep -q "adm"; then
    echo -e "${GREEN}✓${NC} Member of adm group (can read logs)"
    HAS_JOURNAL_ACCESS=true
else
    echo -e "${RED}✗${NC} Not member of systemd-journal or adm group"
    echo -e "${YELLOW}  Fix: sudo usermod -a -G systemd-journal $SERVICE_USER${NC}"
fi
echo ""

# Test journalctl access
echo -e "${BLUE}3. Testing journalctl access:${NC}"
if sudo -u $SERVICE_USER journalctl -n 1 --no-pager &>/dev/null; then
    echo -e "${GREEN}✓${NC} Can read journalctl logs"
else
    echo -e "${RED}✗${NC} Cannot read journalctl logs"
    if [ "$HAS_JOURNAL_ACCESS" = false ]; then
        echo "  This is expected - user needs group membership"
    else
        echo "  User has group membership but still can't read logs"
        echo "  The service may need to be restarted to pick up group changes"
    fi
fi
echo ""

# Check sudoers configuration
echo -e "${BLUE}4. Checking sudo permissions:${NC}"
SUDOERS_FILE="/etc/sudoers.d/otto-bgp-webui"
if [ -f "$SUDOERS_FILE" ]; then
    echo -e "${GREEN}✓${NC} Sudoers file exists: $SUDOERS_FILE"
    
    # Check file permissions
    PERMS=$(stat -c %a "$SUDOERS_FILE")
    if [ "$PERMS" = "440" ]; then
        echo -e "${GREEN}✓${NC} Sudoers file has correct permissions (440)"
    else
        echo -e "${YELLOW}⚠${NC} Sudoers file has permissions $PERMS (should be 440)"
    fi
    
    # Test systemctl sudo access
    if sudo -u $SERVICE_USER sudo -n systemctl status otto-bgp.service &>/dev/null; then
        echo -e "${GREEN}✓${NC} Can use sudo for systemctl commands"
    else
        echo -e "${YELLOW}⚠${NC} Cannot use sudo for systemctl (may not be configured)"
    fi
else
    echo -e "${YELLOW}⚠${NC} Sudoers file not found"
    echo "  Run: sudo ./scripts/setup-service-control.sh"
fi
echo ""

# Check if services are running
echo -e "${BLUE}5. Checking service status:${NC}"
if systemctl is-active --quiet otto-bgp-webui-adapter.service; then
    echo -e "${GREEN}✓${NC} WebUI service is running"
    
    # Get the actual user the service is running as
    ACTUAL_USER=$(ps aux | grep -E "uvicorn.*webui_adapter" | grep -v grep | awk '{print $1}' | head -1)
    if [ -n "$ACTUAL_USER" ]; then
        echo "  Running as user: $ACTUAL_USER"
        if [ "$ACTUAL_USER" != "$SERVICE_USER" ]; then
            echo -e "${YELLOW}⚠${NC} Service is running as $ACTUAL_USER, not $SERVICE_USER"
        fi
    fi
else
    echo -e "${YELLOW}⚠${NC} WebUI service is not running"
fi

if systemctl is-active --quiet otto-bgp.service; then
    echo -e "${GREEN}✓${NC} Otto BGP service is running"
else
    echo -e "${YELLOW}⚠${NC} Otto BGP service is not running"
fi
echo ""

# Summary
echo -e "${BLUE}Summary:${NC}"
echo "========="
if [ "$HAS_JOURNAL_ACCESS" = true ]; then
    echo -e "${GREEN}✓${NC} Log access is properly configured"
else
    echo -e "${RED}✗${NC} Log access needs to be fixed"
    echo ""
    echo "To fix, run:"
    echo "  sudo ./scripts/fix-log-permissions.sh"
fi

# Test actual log retrieval
echo ""
echo -e "${BLUE}6. Testing actual log retrieval:${NC}"
echo "Attempting to get last otto-bgp log entry as $SERVICE_USER:"
echo "---"
sudo -u $SERVICE_USER journalctl -u otto-bgp.service -n 1 --no-pager 2>&1 | head -3
echo "---"
echo ""

echo "Diagnostic complete!"