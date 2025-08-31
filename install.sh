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
REPO_BRANCH="${OTTO_BGP_BRANCH:-main}"  # Allow override with env var
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
    
    # Check for OpenSSL (required for TLS certificates)
    if ! timeout "$TIMEOUT" command -v openssl >/dev/null 2>&1; then
        missing+=("openssl")
        log_warn "OpenSSL not found - required for WebUI TLS certificates"
    fi
    
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
    
    # Check rpki-client for RPKI cache generation
    if timeout "$TIMEOUT" command -v rpki-client >/dev/null 2>&1; then
        log_success "Found rpki-client"
    else
        log_warn "rpki-client not found (optional for RPKI cache generation)"
        log_warn "Install: apt-get install rpki-client (Debian/Ubuntu)"
        log_warn "         dnf install rpki-client (RHEL/CentOS)"
        log_warn "         pkg install rpki-client (FreeBSD)"
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
    mkdir -p "$DATA_DIR"/{ssh-keys,logs,cache,policies,rpki}
    
    # Create WebUI and policy directories
    mkdir -p /usr/local/share/otto-bgp/webui
    mkdir -p "$CONFIG_DIR/tls"
    mkdir -p "$DATA_DIR"/policies/{reports,routers}
    chmod 755 "$CONFIG_DIR/tls"
    
    if [[ "$INSTALL_MODE" == "system" ]]; then
        # Create service user if needed
        if ! id "$SERVICE_USER" &>/dev/null; then
            log_info "Creating service user: $SERVICE_USER"
            sudo useradd -r -s /bin/false -d "$DATA_DIR" "$SERVICE_USER" 2>/dev/null || true
        fi
        
        # Set ownership
        sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR" 2>/dev/null || true
        sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$CONFIG_DIR/tls" \
                      /usr/local/share/otto-bgp/webui 2>/dev/null || true
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
    if ! timeout 120 curl -fsSL "$REPO_URL/archive/$REPO_BRANCH.tar.gz" | tar xz; then
        log_error "Download failed or timed out"
        cd / && rm -rf "$TEMP_DIR"
        exit 1
    fi
    
    # Verify download contents
    if [[ ! -d "otto-bgp-$REPO_BRANCH" ]]; then
        log_error "Download verification failed - otto-bgp-$REPO_BRANCH directory not found"
        cd / && rm -rf "$TEMP_DIR"
        exit 1
    fi
    
    # Move to lib directory (ensure directory exists first)
    mkdir -p "$LIB_DIR"
    if ! mv otto-bgp-$REPO_BRANCH/* "$LIB_DIR/"; then
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
    
    # Install WebUI dependencies (optional, only in system mode)
    if [[ "$INSTALL_MODE" == "system" ]]; then
        log_info "Installing WebUI adapter dependencies..."
        "$VENV_DIR/bin/pip" install --quiet fastapi 'uvicorn[standard]' PyJWT 'passlib[bcrypt]' python-multipart || {
            log_warn "WebUI dependencies installation failed (optional)"
        }
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
    
    # Select source template based on installation mode
    if [[ "$AUTONOMOUS_MODE" == true ]]; then
        TEMPLATE_SOURCE="otto.env.autonomous"
    elif [[ "$INSTALL_MODE" == "system" ]]; then
        TEMPLATE_SOURCE="otto.env.system"
    else
        TEMPLATE_SOURCE="otto.env.user"
    fi
    
    TEMPLATE_PATH="$LIB_DIR/systemd/$TEMPLATE_SOURCE"
    
    # Verify template exists
    if [[ ! -f "$TEMPLATE_PATH" ]]; then
        log_error "Template not found: $TEMPLATE_PATH"
        exit 1
    fi
    
    log_info "Using $TEMPLATE_SOURCE template"
    
    # Copy template as otto.env
    cp "$TEMPLATE_PATH" "$CONFIG_DIR/otto.env"
    
    # Add header with generation info
    sed -i "1i# Generated during installation - $(date)" "$CONFIG_DIR/otto.env"
    sed -i "2i# Customized for $INSTALL_MODE installation\\n" "$CONFIG_DIR/otto.env"
    
    # Replace placeholders with actual values
    if [[ "$INSTALL_MODE" == "user" ]]; then
        # User mode: replace USERNAME_PLACEHOLDER with actual username
        sed -i "s|USERNAME_PLACEHOLDER|$USER|g" "$CONFIG_DIR/otto.env"
    else
        # System/Autonomous mode: replace SERVICE_USER_PLACEHOLDER with service user
        sed -i "s|SERVICE_USER_PLACEHOLDER|$SERVICE_USER_CONFIG|g" "$CONFIG_DIR/otto.env"
    fi
    
    # Additional customizations for autonomous mode
    if [[ "$AUTONOMOUS_MODE" == true ]]; then
        # Replace autonomous-specific placeholders
        sed -i "s|AUTO_APPLY_THRESHOLD_PLACEHOLDER|${AUTO_APPLY_THRESHOLD:-100}|g" "$CONFIG_DIR/otto.env"
        sed -i "s|SMTP_ENABLED_PLACEHOLDER|true|g" "$CONFIG_DIR/otto.env"
        sed -i "s|SMTP_SERVER_PLACEHOLDER|$SMTP_SERVER|g" "$CONFIG_DIR/otto.env"
        sed -i "s|SMTP_PORT_PLACEHOLDER|$SMTP_PORT|g" "$CONFIG_DIR/otto.env"
        sed -i "s|SMTP_USE_TLS_PLACEHOLDER|$SMTP_USE_TLS|g" "$CONFIG_DIR/otto.env"
        sed -i "s|FROM_EMAIL_PLACEHOLDER|$FROM_EMAIL|g" "$CONFIG_DIR/otto.env"
        sed -i "s|TO_EMAILS_PLACEHOLDER|$TO_EMAILS|g" "$CONFIG_DIR/otto.env"
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
    
    # Create RPKI cache update service
    sudo tee /etc/systemd/system/otto-bgp-rpki-update.service > /dev/null << EOF
[Unit]
Description=Otto BGP RPKI Cache Update
Documentation=file://$LIB_DIR/README.md
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$DATA_DIR/rpki
ExecStart=/usr/bin/rpki-client -j -o $DATA_DIR/rpki/vrp_cache.json
StandardOutput=journal
StandardError=journal
NoNewPrivileges=yes
ProtectSystem=strict
PrivateTmp=yes
ReadWritePaths=$DATA_DIR/rpki
EnvironmentFile=-$CONFIG_DIR/otto.env
Environment="RPKI_TRUST_ANCHOR_DIR=/var/lib/rpki-client/ta"

[Install]
WantedBy=multi-user.target
EOF
    
    # Create RPKI cache update timer
    sudo tee /etc/systemd/system/otto-bgp-rpki-update.timer > /dev/null << EOF
[Unit]
Description=Otto BGP RPKI Cache Update Timer
Documentation=file://$LIB_DIR/README.md

[Timer]
OnCalendar=hourly
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
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
    echo "  sudo systemctl enable otto-bgp-rpki-update.service"
    echo "  sudo systemctl enable otto-bgp-rpki-update.timer"
    if [[ "$AUTONOMOUS_MODE" != true ]]; then
        echo "  sudo systemctl enable otto-bgp.timer"
        echo ""
        echo "To start services:"
        echo "  sudo systemctl start otto-bgp-rpki-update.timer"
        echo "  sudo systemctl start otto-bgp.timer"
    else
        echo ""
        echo "To start RPKI updates:"
        echo "  sudo systemctl start otto-bgp-rpki-update.timer"
    fi
}

# TLS generation with OpenSSL compatibility for older versions
generate_self_signed_cert_if_missing() {
    log_info "Checking for TLS certificates..."
    
    CERT_PATH="$CONFIG_DIR/tls/cert.pem"
    KEY_PATH="$CONFIG_DIR/tls/key.pem"
    
    # Skip if both exist
    if [[ -f "$CERT_PATH" && -f "$KEY_PATH" ]]; then
        log_info "TLS certificates already exist - skipping generation"
        return 0
    fi
    
    log_info "Generating self-signed TLS certificate..."
    
    # Get hostname and IP for SAN
    HOST=$(hostname -f 2>/dev/null || hostname)
    IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    
    # Build SAN string
    SAN="DNS:${HOST},DNS:otto-bgp.local,DNS:localhost"
    [[ -n "$IP" ]] && SAN="${SAN},IP:${IP}"
    
    # Create OpenSSL config for compatibility with older versions
    cat > /tmp/otto-openssl.cnf << EOF
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no

[req_distinguished_name]
CN = ${HOST}

[v3_req]
keyUsage = keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = ${HOST}
DNS.2 = localhost
DNS.3 = otto-bgp.local
IP.1 = 127.0.0.1
IP.2 = ${IP:-127.0.0.1}
EOF
    
    # Generate certificate using config file (works with OpenSSL 1.0.2+)
    openssl req -x509 -nodes -days 825 \
        -newkey rsa:4096 \
        -keyout "$KEY_PATH" \
        -out "$CERT_PATH" \
        -config /tmp/otto-openssl.cnf || {
        log_error "Failed to generate TLS certificate - WebUI will not start"
        rm -f /tmp/otto-openssl.cnf
        return 1
    }
    
    rm -f /tmp/otto-openssl.cnf
    
    # Set permissions
    chmod 600 "$KEY_PATH"
    chmod 644 "$CERT_PATH"
    
    if [[ "$INSTALL_MODE" == "system" ]]; then
        sudo chown "$SERVICE_USER:$SERVICE_USER" "$KEY_PATH" "$CERT_PATH" 2>/dev/null || true
    fi
    
    log_success "TLS certificates generated"
}

generate_jwt_secret_if_missing() {
    SECRET_PATH="$CONFIG_DIR/.jwt_secret"
    if [[ -f "$SECRET_PATH" ]]; then
        return 0
    fi
    log_info "Generating JWT secret..."
    umask 177
    head -c 32 /dev/urandom | base64 > "$SECRET_PATH" || {
        log_warn "Failed to generate JWT secret (optional)"
        return 0
    }
    if [[ "$INSTALL_MODE" == "system" ]]; then
        sudo chown "$SERVICE_USER:$SERVICE_USER" "$SECRET_PATH" 2>/dev/null || true
    fi
    chmod 600 "$SECRET_PATH" 2>/dev/null || true
    log_success "JWT secret created"
}

generate_setup_token_if_missing() {
    TOKEN_PATH="$CONFIG_DIR/.setup_token"
    if [[ -f "$TOKEN_PATH" ]]; then
        return 0
    fi
    log_info "Generating one-time Setup token..."
    umask 177
    head -c 32 /dev/urandom | base64 > "$TOKEN_PATH" || {
        log_warn "Failed to generate Setup token (optional)"
        return 0
    }
    if [[ "$INSTALL_MODE" == "system" ]]; then
        sudo chown "$SERVICE_USER:$SERVICE_USER" "$TOKEN_PATH" 2>/dev/null || true
    fi
    chmod 600 "$TOKEN_PATH" 2>/dev/null || true
    log_success "Setup token generated"
}

deploy_webui_frontend() {
    log_info "Deploying WebUI frontend assets..."
    
    if [[ -d "$LIB_DIR/webui/static" ]]; then
        mkdir -p /usr/local/share/otto-bgp/webui
        cp -r "$LIB_DIR/webui/static"/* /usr/local/share/otto-bgp/webui/
        chmod -R 755 /usr/local/share/otto-bgp/webui
        
        if [[ "$INSTALL_MODE" == "system" ]]; then
            sudo chown -R "$SERVICE_USER:$SERVICE_USER" /usr/local/share/otto-bgp/webui 2>/dev/null || true
        fi
        
        log_success "WebUI frontend deployed successfully"
    else
        log_warn "WebUI frontend assets not found - UI will not be available"
    fi
}

deploy_webui_adapter() {
    log_info "Deploying WebUI adapter..."
    
    # Deploy production adapter
    if [[ -f "$LIB_DIR/webui/webui_adapter.py" ]]; then
        cp "$LIB_DIR/webui/webui_adapter.py" "$LIB_DIR/webui_adapter.py"
        chmod 644 "$LIB_DIR/webui_adapter.py"
        log_success "WebUI adapter deployed"
    else
        log_warn "WebUI adapter not found - WebUI will not function"
        return 1
    fi
    
    if [[ "$INSTALL_MODE" == "system" ]]; then
        sudo chown "$SERVICE_USER:$SERVICE_USER" "$LIB_DIR/webui_adapter.py" 2>/dev/null || true
    fi
}

configure_webui_sudo_permissions() {
    log_info "Configuring sudo permissions for service control..."
    
    # Only configure if user wants service control
    if [[ "$OTTO_WEBUI_ENABLE_SERVICE_CONTROL" != "true" ]]; then
        log_info "Service control disabled - skipping sudo configuration"
        return 0
    fi
    
    cat > /tmp/otto-bgp-webui-sudoers << 'EOF'
# Otto BGP WebUI service control permissions
# Allows WebUI to restart services after config changes
otto-bgp ALL=(root) NOPASSWD: /usr/bin/systemctl start otto-bgp.service
otto-bgp ALL=(root) NOPASSWD: /usr/bin/systemctl stop otto-bgp.service
otto-bgp ALL=(root) NOPASSWD: /usr/bin/systemctl restart otto-bgp.service
otto-bgp ALL=(root) NOPASSWD: /usr/bin/systemctl reload otto-bgp.service
otto-bgp ALL=(root) NOPASSWD: /usr/bin/systemctl start otto-bgp-autonomous.service
otto-bgp ALL=(root) NOPASSWD: /usr/bin/systemctl stop otto-bgp-autonomous.service
otto-bgp ALL=(root) NOPASSWD: /usr/bin/systemctl restart otto-bgp-autonomous.service
otto-bgp ALL=(root) NOPASSWD: /usr/bin/systemctl start otto-bgp.timer
otto-bgp ALL=(root) NOPASSWD: /usr/bin/systemctl stop otto-bgp.timer
otto-bgp ALL=(root) NOPASSWD: /usr/bin/systemctl restart otto-bgp.timer
EOF
    
    # Validate sudoers syntax before installing
    if visudo -c -f /tmp/otto-bgp-webui-sudoers >/dev/null 2>&1; then
        sudo mv /tmp/otto-bgp-webui-sudoers /etc/sudoers.d/otto-bgp-webui
        sudo chmod 440 /etc/sudoers.d/otto-bgp-webui
        log_success "Service control permissions configured"
        log_info "To enable: Set OTTO_WEBUI_ENABLE_SERVICE_CONTROL=true in otto.env"
    else
        log_warn "Sudoers validation failed - service restart will require manual intervention"
        rm -f /tmp/otto-bgp-webui-sudoers
    fi
}

create_webui_systemd_service() {
    log_info "Creating WebUI systemd service..."
    
    cat > /tmp/otto-bgp-webui-adapter.service << EOF
[Unit]
Description=Otto BGP WebUI Adapter (Direct TLS)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$LIB_DIR
Environment=PYTHONPATH=$LIB_DIR
Environment=OTTO_WEBUI_ROOT=/usr/local/share/otto-bgp/webui
EnvironmentFile=-$CONFIG_DIR/otto.env
ExecStart=$VENV_DIR/bin/uvicorn webui_adapter:app \
    --host 0.0.0.0 --port 8443 \
    --ssl-certfile $CONFIG_DIR/tls/cert.pem \
    --ssl-keyfile $CONFIG_DIR/tls/key.pem
Restart=on-failure
RestartSec=10
PrivateTmp=yes
ProtectSystem=full
ProtectHome=yes
StandardOutput=journal
StandardError=journal
SyslogIdentifier=otto-bgp-webui

[Install]
WantedBy=multi-user.target
EOF
    
    sudo mv /tmp/otto-bgp-webui-adapter.service /etc/systemd/system/ || {
        log_warn "Failed to install WebUI systemd service (optional)"
        return 0
    }
    
    log_success "WebUI systemd service created"
}

enable_webui_service() {
    log_info "Enabling and starting WebUI service..."
    
    sudo systemctl daemon-reload || {
        log_warn "Failed to reload systemd (optional)"
        return 0
    }
    
    sudo systemctl enable otto-bgp-webui-adapter || {
        log_warn "Failed to enable WebUI service (optional)"
    }
    
    # Start immediately so Setup Wizard is reachable after install
    sudo systemctl start otto-bgp-webui-adapter || {
        log_warn "Failed to start WebUI service (optional)"
    }

    # Onboarding info: URL and setup token hint
    HOSTNAME=$(hostname -f 2>/dev/null || hostname)
    log_info "WebUI running on: https://$HOSTNAME:8443"
    if [[ -f "$CONFIG_DIR/.setup_token" ]]; then
        PREVIEW=$(head -c 8 "$CONFIG_DIR/.setup_token" 2>/dev/null || true)
        log_info "Setup token created at $CONFIG_DIR/.setup_token (preview: ${PREVIEW}...)"
        log_info "Retrieve full token: sudo cat $CONFIG_DIR/.setup_token"
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
    
    # Deploy WebUI components (system mode only)
    if [[ "$INSTALL_MODE" == "system" ]]; then
        generate_self_signed_cert_if_missing
        generate_jwt_secret_if_missing
        generate_setup_token_if_missing
        deploy_webui_adapter
        deploy_webui_frontend        # Deploy pre-built assets from webui/static
        create_webui_systemd_service
        configure_webui_sudo_permissions  # Optional: for service control
        enable_webui_service
    fi
    
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