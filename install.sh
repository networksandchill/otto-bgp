#!/bin/bash
#
# Otto BGP Simplified Installation Script
# 
# Usage:
#   ./install.sh [--user|--system|--autonomous] [--skip-bgpq4]
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
REPO_URL="https://github.com/networksandchill/otto-bgp"
INSTALL_MODE="user"
AUTONOMOUS_MODE=false
SKIP_BGPQ4=false
FORCE_INSTALL=false
TIMEOUT=30

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --system)
            INSTALL_MODE="system"
            shift
            ;;
        --user)
            INSTALL_MODE="user"
            shift
            ;;
        --autonomous)
            INSTALL_MODE="system"
            AUTONOMOUS_MODE=true
            shift
            ;;
        --skip-bgpq4)
            SKIP_BGPQ4=true
            shift
            ;;
        --force)
            FORCE_INSTALL=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--user|--system|--autonomous] [--skip-bgpq4] [--force]"
            echo "Options:"
            echo "  --user        Install for current user (default)"
            echo "  --system      Install system-wide for production"
            echo "  --autonomous  Install with autonomous mode (requires confirmation)"
            echo "  --skip-bgpq4  Skip bgpq4 dependency check"
            echo "  --force       Force installation over existing installation"
            echo ""
            echo "For uninstalling, use the separate uninstall.sh script:"
            echo "  curl -fsSL https://raw.githubusercontent.com/networksandchill/otto-bgp/main/uninstall.sh | sudo bash -s -- --yes"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Set paths
if [[ "$INSTALL_MODE" == "system" ]]; then
    PREFIX="/usr/local"
    BIN_DIR="$PREFIX/bin"
    LIB_DIR="$PREFIX/lib/otto-bgp"
    CONFIG_DIR="/etc/otto-bgp"
    DATA_DIR="/var/lib/otto-bgp"
    SERVICE_USER="otto-bgp"
else
    PREFIX="$HOME/.local"
    BIN_DIR="$PREFIX/bin"
    LIB_DIR="$PREFIX/lib/otto-bgp"
    CONFIG_DIR="$HOME/.config/otto-bgp"
    DATA_DIR="$HOME/.local/share/otto-bgp"
    SERVICE_USER="$USER"
fi

VENV_DIR="$PREFIX/venv"

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

# Check if command exists with timeout
command_exists() {
    timeout "$TIMEOUT" command -v "$1" >/dev/null 2>&1
}

# Check Python with timeout
check_python() {
    log_info "Checking Python..."
    
    if command_exists python3; then
        VERSION=$(timeout "$TIMEOUT" python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))' 2>/dev/null || echo "0.0")
        if [[ "${VERSION//.}" -ge 310 ]]; then
            log_success "Found Python $VERSION"
            return 0
        fi
    fi
    
    log_error "Python 3.10+ required but not found"
    echo "Install Python 3.10+ and retry"
    exit 1
}

# Simplified requirements check with timeouts
check_requirements() {
    log_info "Checking system requirements..."
    
    local missing=()
    
    # Check essential commands with timeout
    for cmd in git curl; do
        if ! timeout "$TIMEOUT" command -v "$cmd" >/dev/null 2>&1; then
            missing+=("$cmd")
        else
            log_success "Found $cmd"
        fi
    done
    
    # Check bgpq4 or containers if not skipped
    if [[ "$SKIP_BGPQ4" == false ]]; then
        if timeout "$TIMEOUT" command -v bgpq4 >/dev/null 2>&1; then
            log_success "Found bgpq4"
        elif timeout "$TIMEOUT" command -v docker >/dev/null 2>&1; then
            log_success "Found docker (will use containerized bgpq4)"
        elif timeout "$TIMEOUT" command -v podman >/dev/null 2>&1; then
            log_success "Found podman (will use containerized bgpq4)"
        else
            log_warn "No bgpq4, docker, or podman found"
            log_warn "Install bgpq4 manually or use containers"
        fi
    fi
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing required tools: ${missing[*]}"
        echo ""
        echo "Install missing dependencies:"
        echo "  # Ubuntu/Debian:"
        echo "  sudo apt-get update && sudo apt-get install -y ${missing[*]}"
        echo "  # RHEL/CentOS/Rocky:"
        echo "  sudo dnf install -y ${missing[*]}"
        echo "  # macOS:"
        echo "  brew install ${missing[*]}"
        exit 1
    fi
    
    log_success "System requirements satisfied"
}

# Create directories
create_directories() {
    log_info "Creating directories..."
    
    mkdir -p "$BIN_DIR" "$LIB_DIR" "$CONFIG_DIR"
    mkdir -p "$DATA_DIR"/{ssh-keys,logs,cache,policies}
    
    if [[ "$INSTALL_MODE" == "system" ]]; then
        # Create service user if needed
        if ! id "$SERVICE_USER" &>/dev/null; then
            log_info "Creating service user: $SERVICE_USER"
            sudo useradd -r -s /bin/false -d "$DATA_DIR" "$SERVICE_USER" 2>/dev/null || true
        fi
        
        # Set ownership
        sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR" 2>/dev/null || true
        sudo chmod 700 "$DATA_DIR/ssh-keys" 2>/dev/null || true
    else
        chmod 700 "$DATA_DIR/ssh-keys" 2>/dev/null || true
    fi
    
    log_success "Directories created"
}

# Check for existing installation
check_existing_installation() {
    # Check if installation already exists
    if [[ -d "$LIB_DIR" ]]; then
        if [[ "$FORCE_INSTALL" == true ]]; then
            log_warn "Existing installation found at $LIB_DIR - removing due to --force flag"
            if [[ "$INSTALL_MODE" == "system" ]]; then
                sudo rm -rf "$LIB_DIR"
            else
                rm -rf "$LIB_DIR"
            fi
        else
            log_error "Existing installation found at $LIB_DIR"
            echo ""
            echo "Options:"
            echo "  1. Force reinstall: add --force flag"
            echo "  2. Uninstall first: curl -fsSL https://raw.githubusercontent.com/networksandchill/otto-bgp/main/uninstall.sh | sudo bash -s -- --yes"
            echo ""
            exit 1
        fi
    fi
}

# Download Otto BGP with timeout
download_otto_bgp() {
    log_info "Downloading Otto BGP..."
    
    # Create temp directory
    TEMP_DIR=$(mktemp -d)
    
    # Ensure cleanup happens even if script exits unexpectedly
    trap 'cd / 2>/dev/null; rm -rf "$TEMP_DIR" 2>/dev/null' EXIT
    
    cd "$TEMP_DIR"
    
    # Download with timeout
    if ! timeout 120 curl -fsSL "$REPO_URL/archive/main.tar.gz" | tar xz; then
        log_error "Download failed or timed out"
        cd / && rm -rf "$TEMP_DIR"
        exit 1
    fi
    
    # Verify download contents
    if [[ ! -d "otto-bgp-main" ]]; then
        log_error "Download verification failed - otto-bgp-main directory not found"
        cd / && rm -rf "$TEMP_DIR"
        exit 1
    fi
    
    # Move to lib directory (ensure directory exists first)
    mkdir -p "$LIB_DIR"
    if ! mv otto-bgp-main/* "$LIB_DIR/"; then
        log_error "Failed to move files to installation directory"
        cd / && rm -rf "$TEMP_DIR"
        exit 1
    fi
    
    # Cleanup
    cd / && rm -rf "$TEMP_DIR"
    trap - EXIT  # Remove the trap since we're cleaning up manually
    
    log_success "Otto BGP downloaded"
}

# Install Python dependencies with timeout
install_python_deps() {
    log_info "Installing Python dependencies..."
    
    # Create virtual environment with timeout
    if ! timeout 60 python3 -m venv "$VENV_DIR"; then
        log_error "Failed to create virtual environment"
        echo "Try: sudo apt-get install python3-venv  # On Ubuntu/Debian"
        exit 1
    fi
    
    # Activate and install
    source "$VENV_DIR/bin/activate"
    
    # Upgrade pip with timeout and proper error handling
    if ! timeout 60 pip install --upgrade pip >/dev/null 2>&1; then
        log_error "Failed to upgrade pip"
        deactivate
        exit 1
    fi
    
    # Install requirements with timeout
    cd "$LIB_DIR"
    if [[ -f requirements.txt ]]; then
        if ! timeout 120 pip install -r requirements.txt; then
            log_error "Failed to install Python dependencies"
            deactivate
            exit 1
        fi
    else
        log_error "requirements.txt not found"
        deactivate
        exit 1
    fi
    
    deactivate
    log_success "Python dependencies installed"
}

# Create executable wrapper
create_wrapper() {
    log_info "Creating executable..."
    
    cat > "$BIN_DIR/otto-bgp" << EOF
#!/bin/bash
# Otto BGP v0.3.2 wrapper script - Unified Pipeline Architecture

# Use venv Python directly without activation
VENV_PYTHON="$VENV_DIR/bin/python"

# Set configuration paths
export OTTO_BGP_CONFIG_DIR="$CONFIG_DIR"
export OTTO_BGP_DATA_DIR="$DATA_DIR"

# Load environment configuration if it exists
if [[ -f "\$OTTO_BGP_CONFIG_DIR/otto.env" ]]; then
    source "\$OTTO_BGP_CONFIG_DIR/otto.env"
fi

# Verify venv Python exists
if [[ ! -f "\$VENV_PYTHON" ]]; then
    echo "Error: Virtual environment Python not found at \$VENV_PYTHON"
    exit 1
fi

# v0.3.2 Unified Pipeline Commands:
# - collect: BGP peer data collection from Juniper devices
# - process: AS number extraction and text processing  
# - policy: BGP policy generation using bgpq4
# - pipeline: Full automated workflow (replaces legacy 3-script process)
# - discover: Router discovery and inspection
# - apply: Policy application with safety controls

# Execute Otto BGP using venv Python with proper working directory
cd "$LIB_DIR"
exec "\$VENV_PYTHON" -m otto_bgp.main "\$@"
EOF
    
    chmod +x "$BIN_DIR/otto-bgp"
    log_success "Executable created at $BIN_DIR/otto-bgp"
}

# Create environment configuration from template
create_config() {
    log_info "Creating environment configuration from template..."
    
    # Determine service user
    if [[ "$INSTALL_MODE" == "system" ]]; then
        SERVICE_USER_CONFIG="otto-bgp"
    else
        SERVICE_USER_CONFIG="$USER"
    fi
    
    # Copy template from example-configs
    if [[ ! -f "$LIB_DIR/example-configs/otto.env.example" ]]; then
        log_error "Template file not found: $LIB_DIR/example-configs/otto.env.example"
        exit 1
    fi
    
    # Copy template and customize with sed
    cp "$LIB_DIR/example-configs/otto.env.example" "$CONFIG_DIR/otto.env"
    
    # Add header with generation info
    sed -i "1i# Generated during installation - $(date)" "$CONFIG_DIR/otto.env"
    sed -i "2i# Customized for $INSTALL_MODE installation\\n" "$CONFIG_DIR/otto.env"
    
    # Customize paths and settings based on installation mode
    if [[ "$INSTALL_MODE" == "system" ]]; then
        # System installation paths
        sed -i "s|OTTO_BGP_ENVIRONMENT=user|OTTO_BGP_ENVIRONMENT=system|g" "$CONFIG_DIR/otto.env"
        sed -i "s|OTTO_BGP_INSTALLATION_MODE=user|OTTO_BGP_INSTALLATION_MODE=system|g" "$CONFIG_DIR/otto.env"
        sed -i "s|OTTO_BGP_SERVICE_USER=username|OTTO_BGP_SERVICE_USER=$SERVICE_USER_CONFIG|g" "$CONFIG_DIR/otto.env"
        sed -i "s|OTTO_BGP_SYSTEMD_ENABLED=false|OTTO_BGP_SYSTEMD_ENABLED=true|g" "$CONFIG_DIR/otto.env"
        sed -i "s|OTTO_BGP_OPTIMIZATION_LEVEL=basic|OTTO_BGP_OPTIMIZATION_LEVEL=enhanced|g" "$CONFIG_DIR/otto.env"
        
        # Update paths for system installation
        sed -i "s|/home/username/.local/share/otto-bgp|$DATA_DIR|g" "$CONFIG_DIR/otto.env"
        sed -i "s|/home/username/.config/otto-bgp|$CONFIG_DIR|g" "$CONFIG_DIR/otto.env"
        sed -i "s|SSH_USERNAME=username|SSH_USERNAME=$SERVICE_USER_CONFIG|g" "$CONFIG_DIR/otto.env"
    else
        # User installation - just update username and paths
        sed -i "s|username|$USER|g" "$CONFIG_DIR/otto.env"
        sed -i "s|/home/$USER/.local/share/otto-bgp|$DATA_DIR|g" "$CONFIG_DIR/otto.env"
        sed -i "s|/home/$USER/.config/otto-bgp|$CONFIG_DIR|g" "$CONFIG_DIR/otto.env"
    fi
    
    # Add autonomous mode configuration if enabled
    if [[ "$AUTONOMOUS_MODE" == true ]]; then
        # Enable autonomous mode in config
        sed -i "s|OTTO_BGP_AUTONOMOUS_ENABLED=false|OTTO_BGP_AUTONOMOUS_ENABLED=true|g" "$CONFIG_DIR/otto.env"
        
        # Uncomment and set autonomous mode options
        sed -i "s|# OTTO_BGP_AUTO_APPLY_THRESHOLD=100|OTTO_BGP_AUTO_APPLY_THRESHOLD=${AUTO_APPLY_THRESHOLD:-100}|g" "$CONFIG_DIR/otto.env"
        sed -i "s|# OTTO_BGP_REQUIRE_CONFIRMATION=true|OTTO_BGP_REQUIRE_CONFIRMATION=true|g" "$CONFIG_DIR/otto.env"
        sed -i "s|# OTTO_BGP_MAX_SESSION_LOSS_PERCENT=5.0|OTTO_BGP_MAX_SESSION_LOSS_PERCENT=5.0|g" "$CONFIG_DIR/otto.env"
        sed -i "s|# OTTO_BGP_MAX_ROUTE_LOSS_PERCENT=10.0|OTTO_BGP_MAX_ROUTE_LOSS_PERCENT=10.0|g" "$CONFIG_DIR/otto.env"
        sed -i "s|# OTTO_BGP_MONITORING_DURATION_SECONDS=300|OTTO_BGP_MONITORING_DURATION_SECONDS=300|g" "$CONFIG_DIR/otto.env"
        
        # Set email configuration
        sed -i "s|# OTTO_BGP_EMAIL_ENABLED=true|OTTO_BGP_EMAIL_ENABLED=true|g" "$CONFIG_DIR/otto.env"
        sed -i "s|# OTTO_BGP_SMTP_SERVER=smtp.company.com|OTTO_BGP_SMTP_SERVER=$SMTP_SERVER|g" "$CONFIG_DIR/otto.env"
        sed -i "s|# OTTO_BGP_SMTP_PORT=587|OTTO_BGP_SMTP_PORT=$SMTP_PORT|g" "$CONFIG_DIR/otto.env"
        sed -i "s|# OTTO_BGP_SMTP_USE_TLS=true|OTTO_BGP_SMTP_USE_TLS=$SMTP_USE_TLS|g" "$CONFIG_DIR/otto.env"
        sed -i "s|# OTTO_BGP_EMAIL_FROM=otto-bgp@company.com|OTTO_BGP_EMAIL_FROM=$FROM_EMAIL|g" "$CONFIG_DIR/otto.env"
        sed -i "s|# OTTO_BGP_EMAIL_TO=network-team@company.com,ops@company.com|OTTO_BGP_EMAIL_TO=$TO_EMAILS|g" "$CONFIG_DIR/otto.env"
        sed -i "s|# OTTO_BGP_EMAIL_SUBJECT_PREFIX=\[Otto BGP Autonomous\]|OTTO_BGP_EMAIL_SUBJECT_PREFIX=[Otto BGP Autonomous]|g" "$CONFIG_DIR/otto.env"
        sed -i "s|# OTTO_BGP_EMAIL_SEND_ON_SUCCESS=true|OTTO_BGP_EMAIL_SEND_ON_SUCCESS=true|g" "$CONFIG_DIR/otto.env"
        sed -i "s|# OTTO_BGP_EMAIL_SEND_ON_FAILURE=true|OTTO_BGP_EMAIL_SEND_ON_FAILURE=true|g" "$CONFIG_DIR/otto.env"
        sed -i "s|# OTTO_BGP_ALERT_ON_MANUAL=true|OTTO_BGP_ALERT_ON_MANUAL=true|g" "$CONFIG_DIR/otto.env"
        sed -i "s|# OTTO_BGP_SUCCESS_NOTIFICATIONS=true|OTTO_BGP_SUCCESS_NOTIFICATIONS=true|g" "$CONFIG_DIR/otto.env"
    fi
    
    # Set appropriate permissions
    if [[ "$INSTALL_MODE" == "system" ]]; then
        sudo chown "$SERVICE_USER_CONFIG:$SERVICE_USER_CONFIG" "$CONFIG_DIR/otto.env"
        sudo chmod 640 "$CONFIG_DIR/otto.env"
    else
        chmod 640 "$CONFIG_DIR/otto.env"
    fi
    
    log_success "Environment configuration created from template at $CONFIG_DIR/otto.env"
}

# Configure autonomous mode
configure_autonomous_mode() {
    if [[ "$AUTONOMOUS_MODE" != true ]]; then
        return 0
    fi
    
    # Check if running in interactive mode (not piped)
    if ! test -t 0; then
        echo ""
        echo -e "${RED}ERROR: Autonomous mode requires interactive setup${NC}"
        echo "======================================================="
        echo "Autonomous mode installation needs to collect SMTP configuration"
        echo "and requires interactive prompts that don't work when piped."
        echo ""
        echo "Please download and run the script locally:"
        echo "  curl -O https://raw.githubusercontent.com/networksandchill/otto-bgp/main/install.sh"
        echo "  chmod +x install.sh"
        echo "  sudo ./install.sh --autonomous"
        echo ""
        echo "See docs/INSTALLATION_GUIDE.md for detailed autonomous setup instructions."
        echo ""
        exit 1
    fi
    
    log_info "Configuring Autonomous Mode..."
    echo ""
    
    # Critical warning
    echo -e "${RED}🚨 AUTONOMOUS MODE SETUP - CRITICAL WARNING${NC}"
    echo "=========================================="
    echo "You are about to enable AUTONOMOUS POLICY APPLICATION."
    echo ""
    echo "This mode will:"
    echo "  • Automatically apply BGP policies to live routers"
    echo "  • Use NETCONF to modify production configurations"
    echo "  • Operate without manual approval for low-risk changes"
    echo ""
    echo -e "${YELLOW}⚠️  OPERATIONAL RISK WARNING:${NC}"
    echo "  • Policy errors can affect network routing"
    echo "  • BGP session changes may impact traffic flow"
    echo "  • Autonomous operation requires careful monitoring"
    echo ""
    
    # Require confirmation
    read -p "Do you understand and accept these risks? (type 'confirm'): " confirmation
    if [[ "$confirmation" != "confirm" ]]; then
        log_error "Autonomous mode setup cancelled"
        exit 1
    fi
    
    # Get auto-apply threshold
    read -p "Maximum prefix count for auto-apply [100]: " threshold
    AUTO_APPLY_THRESHOLD=${threshold:-100}
    
    echo ""
    echo -e "${BLUE}📧 CONFIGURING EMAIL NOTIFICATIONS${NC}"
    echo "=================================="
    echo "Email notifications will be sent for ALL NETCONF events"
    echo "(connections, commits, failures, etc.)"
    echo ""
    
    # SMTP configuration
    read -p "SMTP server [smtp.company.com]: " smtp_server
    SMTP_SERVER=${smtp_server:-smtp.company.com}
    
    read -p "SMTP port [587]: " smtp_port
    SMTP_PORT=${smtp_port:-587}
    
    read -p "Use TLS encryption? [y/N]: " use_tls
    case $use_tls in
        [Yy]* ) SMTP_USE_TLS=true;;
        * ) SMTP_USE_TLS=false;;
    esac
    
    read -p "From email address [otto-bgp@company.com]: " from_email
    FROM_EMAIL=${from_email:-otto-bgp@company.com}
    
    read -p "Engineer email address(es) (comma-separated): " to_emails
    TO_EMAILS="$to_emails"
    
    echo ""
    echo -e "${GREEN}✅ AUTONOMOUS MODE CONFIGURED${NC}"
    echo "   - Auto-apply threshold: $AUTO_APPLY_THRESHOLD prefixes (informational)"
    echo "   - Risk level: low only"
    echo "   - Confirmed commits: enabled"
    echo "   - Email notifications: enabled for ALL NETCONF events"
    echo "   - SMTP server: $SMTP_SERVER:$SMTP_PORT"
    echo "   - TLS encryption: $SMTP_USE_TLS"
    echo "   - From address: $FROM_EMAIL"
    echo "   - Notification recipients: $TO_EMAILS"
    echo "   - Manual approval required for high-risk changes"
    echo ""
    
    log_success "Autonomous mode configuration complete"
}

# Create SystemD services for system installations
create_systemd_services() {
    if [[ "$INSTALL_MODE" != "system" ]]; then
        return 0
    fi
    
    log_info "Creating SystemD services..."
    
    # Create main service file
    sudo tee /etc/systemd/system/otto-bgp.service > /dev/null << EOF
[Unit]
Description=Otto BGP v0.3.2 - Orchestrated Transit Traffic Optimizer
Documentation=file://$LIB_DIR/README.md
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$LIB_DIR
ExecStart=$BIN_DIR/otto-bgp pipeline $CONFIG_DIR/devices.csv --output-dir $DATA_DIR/policies
Environment=PYTHONPATH=$LIB_DIR
EnvironmentFile=-$CONFIG_DIR/otto.env

# Security hardening for v0.3.2
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
RestrictRealtime=yes
RestrictNamespaces=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
RemoveIPC=yes

# Directory access permissions
ReadWritePaths=$DATA_DIR/policies
ReadWritePaths=$DATA_DIR/logs
ReadOnlyPaths=$CONFIG_DIR
ReadOnlyPaths=$LIB_DIR

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=otto-bgp

# Resource limits
TimeoutStartSec=300
TimeoutStopSec=60
MemoryMax=1G
CPUQuota=50%

[Install]
WantedBy=multi-user.target
EOF
    
    # Create timer for scheduled execution (if not autonomous mode)
    if [[ "$AUTONOMOUS_MODE" != true ]]; then
        sudo tee /etc/systemd/system/otto-bgp.timer > /dev/null << EOF
[Unit]
Description=Otto BGP v0.3.2 Scheduled Policy Update
Documentation=file://$LIB_DIR/README.md
Requires=otto-bgp.service

[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
EOF
        log_success "SystemD service and timer created"
    else
        log_success "SystemD service created (autonomous mode - no timer)"
    fi
    
    # Reload systemd daemon
    sudo systemctl daemon-reload
    
    log_info "SystemD services configured. To enable:"
    echo "  sudo systemctl enable otto-bgp.service"
    if [[ "$AUTONOMOUS_MODE" != true ]]; then
        echo "  sudo systemctl enable otto-bgp.timer"
        echo "  sudo systemctl start otto-bgp.timer"
    fi
}

# Main installation
main() {
    echo -e "${BLUE}Otto BGP v0.3.2 Installation - Unified Pipeline Architecture${NC}"
    echo "Mode: $INSTALL_MODE"
    echo "Prefix: $PREFIX"
    echo ""
    
    # Installation workflow for v0.3.2
    check_python
    check_requirements
    configure_autonomous_mode
    check_existing_installation
    create_directories
    download_otto_bgp
    install_python_deps
    create_wrapper
    create_config
    create_systemd_services  # New in v0.3.2
    
    echo ""
    echo -e "${GREEN}✓ Otto BGP v0.3.2 Installation completed successfully!${NC}"
    echo ""
    echo "v0.3.2 Unified Pipeline Commands:"
    echo "  otto-bgp collect devices.csv           # BGP peer data collection"
    echo "  otto-bgp process bgp-data.txt          # AS number extraction"
    echo "  otto-bgp policy input.txt -s           # BGP policy generation"
    echo "  otto-bgp pipeline devices.csv          # Complete automated workflow"
    echo "  otto-bgp discover devices.csv          # Router discovery and inspection"
    echo "  otto-bgp apply policies/               # Policy application with safety"
    echo ""
    echo "Next steps:"
    echo "  1. Add to PATH: export PATH=\"$BIN_DIR:\$PATH\""
    echo "  2. Test v0.3.2: otto-bgp --help"
    echo "  3. Create devices.csv with router details (see example-configs/devices.csv)"
    echo "  4. Setup SSH keys: $LIB_DIR/scripts/setup-host-keys.sh devices.csv"
    if [[ "$INSTALL_MODE" == "system" ]]; then
        echo "  5. Enable SystemD service:"
        echo "     sudo systemctl enable otto-bgp.service"
        if [[ "$AUTONOMOUS_MODE" != true ]]; then
            echo "     sudo systemctl enable otto-bgp.timer"
            echo "     sudo systemctl start otto-bgp.timer"
        fi
        echo "  6. Environment config: $CONFIG_DIR/otto.env"
    else
        echo "  5. Environment config: $CONFIG_DIR/otto.env"
    fi
    echo ""
}

# Cleanup function for error handling
cleanup_on_error() {
    local exit_code=$?
    log_error "Installation failed at line $1"
    
    # Clean up temp directory if it exists
    if [[ -n "${TEMP_DIR:-}" ]] && [[ -d "$TEMP_DIR" ]]; then
        rm -rf "$TEMP_DIR"
        log_info "Cleaned up temporary directory"
    fi
    
    # Clean up partial installation
    if [[ -d "$LIB_DIR" ]]; then
        log_warn "Cleaning up partial installation at $LIB_DIR"
        if [[ "$INSTALL_MODE" == "system" ]]; then
            sudo rm -rf "$LIB_DIR" 2>/dev/null || true
        else
            rm -rf "$LIB_DIR" 2>/dev/null || true
        fi
    fi
    
    # Clean up partial venv
    if [[ -d "$VENV_DIR" ]]; then
        log_warn "Cleaning up partial virtual environment at $VENV_DIR"
        if [[ "$INSTALL_MODE" == "system" ]]; then
            sudo rm -rf "$VENV_DIR" 2>/dev/null || true
        else
            rm -rf "$VENV_DIR" 2>/dev/null || true
        fi
    fi
    
    echo ""
    echo -e "${RED}Installation failed. Partial files have been cleaned up.${NC}"
    echo "For troubleshooting, check:"
    echo "  • Network connectivity"
    echo "  • Disk space availability"
    echo "  • Required permissions"
    echo ""
    echo "To clean any remaining files, run:"
    echo "  curl -fsSL https://raw.githubusercontent.com/networksandchill/otto-bgp/main/uninstall.sh | sudo bash -s -- --force-cleanup"
    
    exit $exit_code
}

# Error handling
trap 'cleanup_on_error $LINENO' ERR

# Run installation
main "$@"