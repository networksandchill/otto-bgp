#!/bin/bash
#
# Otto BGP Uninstallation Script
#
# Usage:
#   ./uninstall.sh [options]
#
# Options:
#   --yes               Skip confirmation prompt
#   --keep-config       Keep configuration files
#   --keep-data         Keep data files (logs, cache, policies)
#   --complete          Remove everything including backups
#   --force-cleanup     Remove partial/broken installations
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Options
SKIP_CONFIRM=false
KEEP_CONFIG=false
KEEP_DATA=false
COMPLETE_REMOVAL=false
FORCE_CLEANUP=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --yes|-y)
            SKIP_CONFIRM=true
            shift
            ;;
        --keep-config)
            KEEP_CONFIG=true
            shift
            ;;
        --keep-data)
            KEEP_DATA=true
            shift
            ;;
        --complete)
            COMPLETE_REMOVAL=true
            shift
            ;;
        --force-cleanup)
            FORCE_CLEANUP=true
            SKIP_CONFIRM=true  # Auto-skip confirmation for force cleanup
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Detect installation
find_installation() {
    # Check common locations for binary first
    if [[ -f "$HOME/.local/bin/otto-bgp" ]]; then
        INSTALL_MODE="user"
        PREFIX="$HOME/.local"
    elif [[ -f "/usr/local/bin/otto-bgp" ]]; then
        INSTALL_MODE="system"
        PREFIX="/usr/local"
    # If no binary found, check for partial installations (lib directories)
    elif [[ -d "$HOME/.local/lib/otto-bgp" ]]; then
        INSTALL_MODE="user"
        PREFIX="$HOME/.local"
        echo -e "${YELLOW}Found partial user installation (no binary)${NC}"
    elif [[ -d "/usr/local/lib/otto-bgp" ]]; then
        INSTALL_MODE="system"
        PREFIX="/usr/local"
        echo -e "${YELLOW}Found partial system installation (no binary)${NC}"
    # Check for other installation artifacts
    elif [[ -d "$HOME/.config/otto-bgp" ]] || [[ -d "$HOME/.local/share/otto-bgp" ]]; then
        INSTALL_MODE="user"
        PREFIX="$HOME/.local"
        echo -e "${YELLOW}Found user installation artifacts${NC}"
    elif [[ -d "/etc/otto-bgp" ]] || [[ -d "/var/lib/otto-bgp" ]]; then
        INSTALL_MODE="system"
        PREFIX="/usr/local"
        echo -e "${YELLOW}Found system installation artifacts${NC}"
    else
        if [[ "$FORCE_CLEANUP" == true ]]; then
            echo -e "${YELLOW}No installation found, but --force-cleanup specified${NC}"
            echo -e "${YELLOW}Will attempt to clean any remaining otto-bgp files${NC}"
            INSTALL_MODE="unknown"
            PREFIX="/usr/local"  # Default to system for cleanup
        else
            echo -e "${RED}Otto BGP installation not found${NC}"
            echo ""
            echo "If you have a broken installation, try:"
            echo "  $0 --force-cleanup"
            exit 1
        fi
    fi
    
    # Set paths based on installation
    BIN_DIR="$PREFIX/bin"
    LIB_DIR="$PREFIX/lib/otto-bgp"
    
    if [[ "$INSTALL_MODE" == "system" ]]; then
        CONFIG_DIR="/etc/otto-bgp"
        DATA_DIR="/var/lib/otto-bgp"
        VENV_DIR="/usr/local/venv"
    elif [[ "$INSTALL_MODE" == "user" ]]; then
        CONFIG_DIR="$HOME/.config/otto-bgp"
        DATA_DIR="$HOME/.local/share/otto-bgp"
        VENV_DIR="$HOME/.local/venv"
    else
        # Force cleanup mode - check all possible locations
        CONFIG_DIR="/etc/otto-bgp"
        DATA_DIR="/var/lib/otto-bgp"
        VENV_DIR="/usr/local/venv"
    fi
}

# Show what will be removed
show_removal_plan() {
    echo -e "${YELLOW}Otto BGP Uninstallation${NC}"
    echo "========================"
    echo ""
    echo "Found installation: $INSTALL_MODE mode at $PREFIX"
    echo ""
    echo "Will remove:"
    [[ -f "$BIN_DIR/otto-bgp" ]] && echo "  • Binary: $BIN_DIR/otto-bgp"
    [[ -d "$LIB_DIR" ]] && echo "  • Libraries: $LIB_DIR"
    [[ -d "$VENV_DIR" ]] && echo "  • Virtual environment: $VENV_DIR"
    
    if [[ "$KEEP_CONFIG" == false ]]; then
        [[ -d "$CONFIG_DIR" ]] && echo "  • Configuration: $CONFIG_DIR"
    fi
    
    if [[ "$KEEP_DATA" == false ]]; then
        [[ -d "$DATA_DIR" ]] && echo "  • Data: $DATA_DIR"
    fi
    
    # Show additional cleanup for force mode
    if [[ "$FORCE_CLEANUP" == true ]]; then
        echo ""
        echo -e "${YELLOW}Force cleanup mode - will also check:${NC}"
        echo "  • User installations: $HOME/.local/bin/otto-bgp, $HOME/.local/lib/otto-bgp"
        echo "  • User config: $HOME/.config/otto-bgp"
        echo "  • User data: $HOME/.local/share/otto-bgp"
        echo "  • Any remaining otto-bgp processes"
    fi
    
    if [[ "$INSTALL_MODE" == "system" ]] && systemctl list-units --full -all | grep -Fq "otto-bgp"; then
        echo "  • Systemd services"
    fi
    
    echo ""
    
    if [[ "$KEEP_CONFIG" == true ]] || [[ "$KEEP_DATA" == true ]]; then
        echo -e "${YELLOW}Keeping:${NC}"
        [[ "$KEEP_CONFIG" == true ]] && echo "  • Configuration files"
        [[ "$KEEP_DATA" == true ]] && echo "  • Data files (logs, policies, etc.)"
        echo ""
    fi
}

# Confirmation
confirm_removal() {
    if [[ "$SKIP_CONFIRM" == false ]]; then
        read -p "Continue with uninstallation? [y/N]: " response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            echo "Uninstallation cancelled"
            exit 0
        fi
    fi
}

# Remove systemd services
remove_systemd_services() {
    if [[ "$INSTALL_MODE" == "system" ]] && [[ -f /etc/systemd/system/otto-bgp.service ]]; then
        echo "Removing systemd services..."
        sudo systemctl stop otto-bgp.timer 2>/dev/null || true
        sudo systemctl stop otto-bgp.service 2>/dev/null || true
        sudo systemctl disable otto-bgp.timer 2>/dev/null || true
        sudo systemctl disable otto-bgp.service 2>/dev/null || true
        sudo rm -f /etc/systemd/system/otto-bgp.service
        sudo rm -f /etc/systemd/system/otto-bgp.timer
        sudo systemctl daemon-reload
        echo -e "${GREEN}✓${NC} Systemd services removed"
    fi
}

# Perform uninstallation
perform_uninstall() {
    echo ""
    echo "Uninstalling Otto BGP..."
    
    # Remove binary
    if [[ -f "$BIN_DIR/otto-bgp" ]]; then
        if [[ "$INSTALL_MODE" == "system" ]]; then
            sudo rm -f "$BIN_DIR/otto-bgp"
        else
            rm -f "$BIN_DIR/otto-bgp"
        fi
        echo -e "${GREEN}✓${NC} Binary removed"
    fi
    
    # Remove libraries
    if [[ -d "$LIB_DIR" ]]; then
        if [[ "$INSTALL_MODE" == "system" ]]; then
            sudo rm -rf "$LIB_DIR"
        else
            rm -rf "$LIB_DIR"
        fi
        echo -e "${GREEN}✓${NC} Libraries removed"
    fi
    
    # Remove virtual environment
    if [[ -d "$VENV_DIR" ]]; then
        if [[ "$INSTALL_MODE" == "system" ]]; then
            sudo rm -rf "$VENV_DIR"
        else
            rm -rf "$VENV_DIR"
        fi
        echo -e "${GREEN}✓${NC} Virtual environment removed"
    fi
    
    # Remove configuration
    if [[ "$KEEP_CONFIG" == false ]] && [[ -d "$CONFIG_DIR" ]]; then
        if [[ "$INSTALL_MODE" == "system" ]]; then
            sudo rm -rf "$CONFIG_DIR"
        else
            rm -rf "$CONFIG_DIR"
        fi
        echo -e "${GREEN}✓${NC} Configuration removed"
    fi
    
    # Remove data
    if [[ "$KEEP_DATA" == false ]] && [[ -d "$DATA_DIR" ]]; then
        if [[ "$COMPLETE_REMOVAL" == true ]]; then
            # Remove everything including backups
            if [[ "$INSTALL_MODE" == "system" ]]; then
                sudo rm -rf "$DATA_DIR"
            else
                rm -rf "$DATA_DIR"
            fi
            echo -e "${GREEN}✓${NC} All data removed (including backups)"
        else
            # Keep backups, remove everything else
            if [[ -d "$DATA_DIR/backups" ]]; then
                echo -e "${YELLOW}!${NC} Keeping backups at $DATA_DIR/backups"
                find "$DATA_DIR" -mindepth 1 -maxdepth 1 ! -name 'backups' -exec rm -rf {} +
            else
                if [[ "$INSTALL_MODE" == "system" ]]; then
                    sudo rm -rf "$DATA_DIR"
                else
                    rm -rf "$DATA_DIR"
                fi
            fi
            echo -e "${GREEN}✓${NC} Data removed"
        fi
    fi
    
    # Remove service user (system mode only)
    if [[ "$INSTALL_MODE" == "system" ]] && id "otto-bgp" &>/dev/null; then
        if [[ "$COMPLETE_REMOVAL" == true ]]; then
            sudo userdel otto-bgp 2>/dev/null || true
            echo -e "${GREEN}✓${NC} Service user removed"
        fi
    fi
    
    # Force cleanup mode - remove any remaining files
    if [[ "$FORCE_CLEANUP" == true ]]; then
        echo ""
        echo "Performing force cleanup..."
        
        # Determine actual user home when run with sudo
        if [[ -n "${SUDO_USER:-}" ]] && [[ "$SUDO_USER" != "root" ]]; then
            ACTUAL_USER_HOME="/home/$SUDO_USER"
        else
            ACTUAL_USER_HOME="$HOME"
        fi
        
        # Check and remove user installations (both current $HOME and actual user home)
        for USER_HOME in "$HOME" "$ACTUAL_USER_HOME"; do
            # Skip if it's the same directory to avoid duplicate work
            [[ "$HOME" == "$ACTUAL_USER_HOME" ]] && [[ "$USER_HOME" == "$ACTUAL_USER_HOME" ]] && continue
            
            if [[ -f "$USER_HOME/.local/bin/otto-bgp" ]]; then
                rm -f "$USER_HOME/.local/bin/otto-bgp"
                echo -e "${GREEN}✓${NC} Removed user binary from $USER_HOME"
            fi
            
            if [[ -d "$USER_HOME/.local/lib/otto-bgp" ]]; then
                rm -rf "$USER_HOME/.local/lib/otto-bgp"
                echo -e "${GREEN}✓${NC} Removed user libraries from $USER_HOME"
            fi
            
            if [[ -d "$USER_HOME/.local/venv" ]]; then
                rm -rf "$USER_HOME/.local/venv"
                echo -e "${GREEN}✓${NC} Removed user virtual environment from $USER_HOME"
            fi
            
            if [[ -d "$USER_HOME/.config/otto-bgp" ]]; then
                rm -rf "$USER_HOME/.config/otto-bgp"
                echo -e "${GREEN}✓${NC} Removed user configuration from $USER_HOME"
            fi
            
            if [[ -d "$USER_HOME/.local/share/otto-bgp" ]]; then
                rm -rf "$USER_HOME/.local/share/otto-bgp"
                echo -e "${GREEN}✓${NC} Removed user data from $USER_HOME"
            fi
        done
        
        # Kill any running otto-bgp processes
        if pgrep -f "otto-bgp" >/dev/null 2>&1; then
            pkill -f "otto-bgp" 2>/dev/null || true
            echo -e "${GREEN}✓${NC} Stopped otto-bgp processes"
        fi
        
        echo -e "${GREEN}✓${NC} Force cleanup completed"
    fi
}

# Main
main() {
    find_installation
    show_removal_plan
    confirm_removal
    remove_systemd_services
    perform_uninstall
    
    echo ""
    echo -e "${GREEN}Otto BGP has been uninstalled${NC}"
    
    if [[ "$KEEP_CONFIG" == true ]] || [[ "$KEEP_DATA" == true ]]; then
        echo ""
        echo "Preserved files:"
        [[ "$KEEP_CONFIG" == true ]] && [[ -d "$CONFIG_DIR" ]] && echo "  • Config: $CONFIG_DIR"
        [[ "$KEEP_DATA" == true ]] && [[ -d "$DATA_DIR" ]] && echo "  • Data: $DATA_DIR"
    fi
    
    echo ""
    echo "Thank you for using Otto BGP!"
}

main