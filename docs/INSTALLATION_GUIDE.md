# Otto BGP Installation Guide

## Overview

Otto BGP v0.3.2 introduces a three-tier installation system that separates installation complexity from operational risk, providing flexible deployment options for different environments and risk tolerance levels.

**Installation Philosophy**: Clear separation between installation modes and operational capabilities with mandatory safety confirmation for autonomous features.

## Three-Tier Installation System

### Installation Modes

| Mode | Target Use | Installation Scope | Autonomous Support | Safety Level |
|------|------------|-------------------|-------------------|--------------|
| **User** | Development/Testing | Local user directory | ❌ | Basic |
| **System** | Production | System-wide with optimizations | ✅ Manual Only | Enhanced |
| **Autonomous** | Hands-off Operations | System-wide + autonomous config | ✅ Full Auto | Maximum |

### Mode Comparison

```
┌─────────────────────────────────────────────────────────────────┐
│                 Otto BGP Installation Modes                     │
├─────────────────┬─────────────────┬─────────────────────────────┤
│   USER MODE     │   SYSTEM MODE   │    AUTONOMOUS MODE          │
│                 │                 │                             │
│ • Local install │ • System-wide   │ • System-wide installation  │
│ • Dev/testing   │ • Production    │ • Autonomous operation      │
│ • Basic safety  │ • Enhanced      │ • Email audit trail        │
│ • Manual only   │   safety        │ • Risk-based decisions     │
│                 │ • Manual apply  │ • Mandatory confirmation    │
└─────────────────┴─────────────────┴─────────────────────────────┘
```

## Prerequisites

### System Requirements

**Minimum Requirements:**
- Linux/macOS operating system
- Python 3.9+ with pip
- SSH client
- 1GB free disk space

**Production Requirements (System/Autonomous modes):**
- systemd-based Linux distribution
- sudo/root access for system installation
- Dedicated service user recommended
- SMTP server for email notifications (autonomous mode)
- 4GB+ free disk space

### Dependencies

**Core Dependencies:**
```bash
# Python packages
pip install junos-eznc paramiko PyYAML pandas

# System packages (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install -y python3-dev python3-pip openssh-client

# System packages (RHEL/CentOS)
sudo yum install -y python3-devel python3-pip openssh-clients

# bgpq4 (required for policy generation)
# Installation instructions: https://github.com/bgp/bgpq4
```

**Development Dependencies:**
```bash
pip install black mypy bandit safety
```

## Installation Methods

### Quick Installation

```bash
# Download and run installer
curl -fsSL https://raw.githubusercontent.com/networksandchill/otto-bgp/main/install.sh | bash

# Or clone and install
git clone https://github.com/networksandchill/otto-bgp.git
cd otto-bgp
./install.sh
```

### Installation Modes

#### 1. User Mode Installation (Default)

**Purpose**: Development, testing, and local usage

```bash
# Default installation (user mode)
./install.sh

# Explicit user mode
./install.sh --user
```

**What it does:**
- Installs to `~/.local/bin/otto-bgp`
- Creates configuration in `~/.otto-bgp/`
- Uses local Python environment
- No system modifications
- Basic safety controls only

**Configuration created:**

*Note: The following JSON represents the conceptual configuration. Actual configuration is stored in `~/.config/otto-bgp/otto.env` using KEY=value format.*

```json
{
  "environment": "user",
  "installation_mode": {
    "type": "user",
    "service_user": "current_user",
    "systemd_enabled": false,
    "optimization_level": "basic"
  },
  "autonomous_mode": {
    "enabled": false
  }
}
```

#### 2. System Mode Installation

**Purpose**: Production deployment with enhanced safety controls

```bash
./install.sh --system
```

**What it does:**
- Installs to `/opt/otto-bgp/`
- Creates configuration in `/etc/otto-bgp/`
- Creates service user `otto.bgp`
- Sets up systemd service (optional)
- Enhanced security and performance optimizations
- Autonomous mode available but disabled

**System Setup:**
```bash
# Creates service user
sudo useradd -r -s /bin/false -d /var/lib/otto-bgp otto.bgp

# Creates directories
sudo mkdir -p /etc/otto-bgp
sudo mkdir -p /var/lib/otto-bgp/{policies,logs,ssh-keys}
sudo mkdir -p /var/log/otto-bgp

# Sets permissions
sudo chown -R otto.bgp:otto.bgp /var/lib/otto-bgp
sudo chown -R otto.bgp:otto.bgp /var/log/otto-bgp
sudo chmod 750 /etc/otto-bgp
sudo chmod 700 /var/lib/otto-bgp/ssh-keys
```

**Configuration created:**

*Note: The following JSON represents the conceptual configuration. Actual configuration is stored in `/etc/otto-bgp/otto.env` using KEY=value format.*

```json
{
  "environment": "system",
  "installation_mode": {
    "type": "system",
    "service_user": "otto.bgp",
    "systemd_enabled": true,
    "optimization_level": "enhanced"
  },
  "autonomous_mode": {
    "enabled": false,
    "auto_apply_threshold": 100,
    "require_confirmation": true,
    "safety_overrides": {
      "max_session_loss_percent": 5.0,
      "max_route_loss_percent": 10.0,
      "monitoring_duration_seconds": 300
    }
  }
}
```

#### 3. Autonomous Mode Installation

**Purpose**: Hands-off operations with complete automation

**⚠️ Interactive Setup Required:**
Autonomous mode requires interactive configuration that cannot be done through piped installation.

```bash
# Download and run locally (required for autonomous mode)
curl -O https://raw.githubusercontent.com/networksandchill/otto-bgp/main/install.sh
chmod +x install.sh
./install.sh --autonomous
```

**⚠️ Critical Safety Warning:**
This mode enables automatic policy application. Mandatory confirmation required.

**Interactive Setup Process:**
```bash
🚨 AUTONOMOUS MODE SETUP - CRITICAL WARNING
==========================================
You are about to enable AUTONOMOUS POLICY APPLICATION.

This mode will:
  • Automatically apply BGP policies to live routers
  • Use NETCONF to modify production configurations  
  • Operate without manual approval for low-risk changes

⚠️  OPERATIONAL RISK WARNING:
  • Policy errors can affect network routing
  • BGP session changes may impact traffic flow
  • Autonomous operation requires careful monitoring

Do you understand and accept these risks? (type 'confirm'): confirm

Maximum prefix count for auto-apply [100]: 150

📧 CONFIGURING EMAIL NOTIFICATIONS
==================================
Email notifications will be sent for ALL NETCONF events
(connections, commits, failures, etc.)

SMTP server [smtp.company.com]: smtp.company.com
SMTP port [587]: 587
Use TLS encryption? [y/N]: y
From email address [otto-bgp@company.com]: otto-bgp@company.com
Engineer email address(es) (comma-separated): network-team@company.com,ops@company.com

✅ AUTONOMOUS MODE CONFIGURED
   - Auto-apply threshold: 150 prefixes (informational)
   - Risk level: low only
   - Confirmed commits: enabled
   - Email notifications: enabled for ALL NETCONF events
   - SMTP server: smtp.company.com:587
   - Notification recipients: network-team@company.com,ops@company.com
   - Manual approval required for high-risk changes
```

**Complete Configuration Created:**

*Note: The following JSON represents the conceptual configuration. Actual configuration is stored in `/etc/otto-bgp/otto.env` using KEY=value format.*

```json
{
  "environment": "system", 
  "installation_mode": {
    "type": "system",
    "service_user": "otto.bgp",
    "systemd_enabled": true,
    "optimization_level": "enhanced"
  },
  "autonomous_mode": {
    "enabled": true,
    "auto_apply_threshold": 150,
    "require_confirmation": true,
    "safety_overrides": {
      "max_session_loss_percent": 5.0,
      "max_route_loss_percent": 10.0,
      "monitoring_duration_seconds": 300
    },
    "notifications": {
      "email": {
        "enabled": true,
        "smtp_server": "smtp.company.com",
        "smtp_port": 587,
        "smtp_use_tls": true,
        "from_address": "otto-bgp@company.com",
        "to_addresses": ["network-team@company.com", "ops@company.com"],
        "subject_prefix": "[Otto BGP Autonomous]",
        "send_on_success": true,
        "send_on_failure": true
      },
      "alert_on_manual": true,
      "success_notifications": true
    }
  }
}
```

## Installation Script Reference

### install.sh Command Line Options

```bash
./install.sh [OPTIONS]

OPTIONS:
  --user               Install in user mode (default)
  --system             Install in system mode for production
  --autonomous         Install with autonomous mode (requires confirmation)
  --production         DEPRECATED: Use --system (shows warning)
  
  --skip-deps          Skip dependency installation
  --skip-service       Skip systemd service setup (system mode)
  --skip-ssh-keys      Skip SSH host key setup
  --config-only        Only create/update configuration
  
  --service-user USER  Custom service user (default: otto.bgp)
  --config-dir DIR     Custom configuration directory
  --data-dir DIR       Custom data directory
  
  --force              Force installation (overwrite existing)
  --verbose            Verbose installation output
  --help               Show this help message
```

### Installation Process Flow

```bash
# 1. Dependency Check and Installation
check_dependencies()
install_python_packages()
install_bgpq4()

# 2. Mode-Specific Setup
if [[ "$INSTALL_MODE" == "user" ]]; then
    setup_user_mode()
elif [[ "$INSTALL_MODE" == "system" ]]; then
    setup_system_mode()
    if [[ "$AUTONOMOUS_MODE" == true ]]; then
        setup_autonomous_mode()
    fi
fi

# 3. Configuration Creation
create_default_config()
configure_ssh_security()

# 4. Service Setup (system mode only)
if [[ "$SYSTEM_MODE" == true && "$SKIP_SERVICE" == false ]]; then
    setup_systemd_service()
fi

# 5. Validation and Completion
validate_installation()
display_completion_message()
```

## Manual Production Deployment

For environments requiring manual installation or custom configurations, follow these detailed production deployment steps.

### Production System Requirements

**Operating System**: Debian 12 (Bookworm) or Ubuntu 22.04+
**Hardware**: 4 vCPU, 8GB RAM, 100GB storage
**Network**: Outbound HTTPS (bgpq4 queries), SSH to target devices

### Step-by-Step Deployment

#### 1. System Preparation

**For Debian 12 / Ubuntu 22.04+:**
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3 python3-pip python3-venv git openssh-client systemd podman
# Install bgpq4
sudo apt install bgpq4  # If available
# OR build from source: https://github.com/bgp/bgpq4

# Verify bgpq4 installation
bgpq4 --help
which bgpq4  # Should show /usr/bin/bgpq4
```

**For RHEL 9+ / CentOS Stream 9+ / Rocky Linux 9+ / AlmaLinux 9+:**
```bash
# Update system
sudo dnf update -y

# Enable EPEL repository (required for bgpq4)
sudo dnf install -y epel-release

# Install dependencies
sudo dnf install -y python3 python3-pip python3-venv git openssh-clients systemd podman

# Install bgpq4 from EPEL
sudo dnf install -y bgpq4

# Verify bgpq4 installation
bgpq4 --help
which bgpq4  # Should show /usr/bin/bgpq4
```

**Note:** The Otto BGP installation script will automatically handle EPEL repository setup for RHEL-based systems when needed.

#### 2. User and Directory Setup
```bash
# Create dedicated system user
sudo useradd --system --shell /bin/false --home /var/lib/otto-bgp \
    --create-home otto-bgp

# Create directory structure
sudo mkdir -p /opt/otto-bgp
sudo mkdir -p /var/lib/otto-bgp/{logs,policies,ssh-keys}
sudo mkdir -p /etc/otto-bgp

# Set ownership
sudo chown -R otto-bgp:otto-bgp /var/lib/otto-bgp
sudo chown otto-bgp:otto-bgp /opt/otto-bgp
```

#### 3. Application Deployment
```bash
# Clone repository
sudo git clone https://github.com/networksandchill/otto-bgp.git /opt/otto-bgp
cd /opt/otto-bgp

# Create virtual environment as otto-bgp user
sudo -u otto-bgp python3 -m venv /var/lib/otto-bgp/venv

# Install dependencies
sudo -u otto-bgp /var/lib/otto-bgp/venv/bin/pip install -r requirements.txt

# Make CLI executable
sudo chmod +x /opt/otto-bgp/otto-bgp

# Create symlink for system-wide access
sudo ln -sf /opt/otto-bgp/otto-bgp /usr/local/bin/otto-bgp
```

#### 4. SSH Key Configuration
```bash
# Generate SSH key for otto-bgp user
sudo -u otto-bgp ssh-keygen -t ed25519 -f /var/lib/otto-bgp/ssh-keys/otto-bgp \
    -N "" -C "otto-bgp@$(hostname)"

# Set proper permissions
sudo chmod 600 /var/lib/otto-bgp/ssh-keys/otto-bgp
sudo chmod 644 /var/lib/otto-bgp/ssh-keys/otto-bgp.pub

# Display public key for deployment to network devices
echo "Deploy this public key to your network devices:"
sudo cat /var/lib/otto-bgp/ssh-keys/otto-bgp.pub
```

#### 4a. SSH Host Key Verification Setup (CRITICAL SECURITY STEP)
```bash
# IMPORTANT: This step collects SSH host keys from your network devices
# to prevent man-in-the-middle attacks. Run this AFTER deploying SSH keys
# to your devices but BEFORE production deployment.

# Method 1: Use the provided setup script (recommended)
sudo chmod +x /opt/otto-bgp/scripts/setup-host-keys.sh
sudo /opt/otto-bgp/scripts/setup-host-keys.sh \
    /var/lib/otto-bgp/config/devices.csv \
    /var/lib/otto-bgp/ssh-keys/known_hosts

# Method 2: Use Python setup script with Otto
sudo -u otto-bgp /var/lib/otto-bgp/venv/bin/python \
    /opt/otto-bgp/scripts/setup_host_keys.py \
    --devices /var/lib/otto-bgp/config/devices.csv \
    --output /var/lib/otto-bgp/ssh-keys/known_hosts

# Verify collected host keys (shows fingerprints)
sudo -u otto-bgp ssh-keygen -l -f /var/lib/otto-bgp/ssh-keys/known_hosts

# SECURITY VERIFICATION: Compare these fingerprints with your network team's records
# Each device should have a unique fingerprint that matches your documentation

# Test connection with strict host checking (replace with actual device)
sudo -u otto-bgp ssh -i /var/lib/otto-bgp/ssh-keys/otto-bgp \
    -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile=/var/lib/otto-bgp/ssh-keys/known_hosts \
    bgp-read@192.168.1.1 "show version"
```

#### 5. Configuration Setup
```bash
# Create environment configuration file (for system mode)
sudo cp /opt/otto-bgp/systemd/otto.env.system /etc/otto-bgp/otto.env

# Customize configuration
sudo nano /etc/otto-bgp/otto.env

# Replace placeholder values
sudo sed -i "s|SERVICE_USER_PLACEHOLDER|otto-bgp|g" /etc/otto-bgp/otto.env

# Set proper permissions
sudo chown otto-bgp:otto-bgp /etc/otto-bgp/otto.env
sudo chmod 640 /etc/otto-bgp/otto.env
```

**Key configuration variables to customize:**
```bash
# SSH Configuration
SSH_USERNAME=bgp-read
OTTO_BGP_SSH_PRIVATE_KEY=/var/lib/otto-bgp/ssh-keys/otto-bgp
OTTO_BGP_SSH_KNOWN_HOSTS=/var/lib/otto-bgp/ssh-keys/known_hosts

# BGPq4 Configuration  
OTTO_BGP_BGPQ4_MODE=auto
OTTO_BGP_BGPQ4_TIMEOUT=45

# Logging Configuration
OTTO_BGP_LOG_LEVEL=INFO
OTTO_BGP_LOG_FILE=/var/lib/otto-bgp/logs/otto-bgp.log
```

#### 6. Device Inventory Setup
```bash
# Create devices.csv with your network devices
sudo tee /var/lib/otto-bgp/devices.csv << 'EOF'
address,hostname
192.168.1.1,core-router-1
192.168.1.2,core-router-2  
10.0.1.10,edge-router-1
EOF

# Set ownership
sudo chown otto-bgp:otto-bgp /var/lib/otto-bgp/devices.csv
```

## SSH Host Key Setup

### Security Requirements

Otto BGP v0.3.2 implements strict host key verification for all SSH connections.

#### Initial Host Key Collection

**⚠️ Setup Mode - One-time use only:**
```bash
# Run BEFORE production deployment
./scripts/setup-host-keys.sh

# This script:
# 1. Connects to each router in devices.csv
# 2. Collects and verifies SSH host keys
# 3. Saves to /var/lib/otto-bgp/ssh-keys/known_hosts
# 4. Sets proper permissions (600)
```

**Setup Script Process:**
```bash
#!/bin/bash
# ./scripts/setup-host-keys.sh

# CRITICAL: Only run during initial setup
if [[ "$OTTO_BGP_SETUP_MODE" != "true" ]]; then
    echo "ERROR: Setup mode not enabled"
    echo "Set OTTO_BGP_SETUP_MODE=true ONLY during initial setup"
    exit 1
fi

# Process each router
while IFS=',' read -r hostname address username model location; do
    echo "Collecting host key for $hostname ($address)..."
    
    # Collect host key
    ssh-keyscan -H "$address" >> "$KNOWN_HOSTS_FILE"
    
    # Verify key was collected
    if ssh-keygen -F "$address" -f "$KNOWN_HOSTS_FILE" >/dev/null; then
        echo "✅ Host key collected for $address"
    else
        echo "❌ Failed to collect host key for $address"
    fi
done < devices.csv

# Set secure permissions
chmod 600 "$KNOWN_HOSTS_FILE"
chown otto.bgp:otto.bgp "$KNOWN_HOSTS_FILE"

echo "✅ Host key setup complete"
echo "⚠️  IMPORTANT: Disable setup mode immediately"
echo "   unset OTTO_BGP_SETUP_MODE"
```

#### Production Host Key Verification

```python
# Strict verification in production
class StrictHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    def missing_host_key(self, client, hostname, key):
        key_type = key.get_name()
        fingerprint = key.get_fingerprint().hex()
        
        logger.error(f"Host key verification failed for {hostname}")
        logger.error(f"Unknown {key_type} key: {fingerprint}")
        
        raise paramiko.SSHException(f"Host key verification failed for {hostname}")
```

#### Host Key Management

```bash
# Verify collected host keys
ssh-keygen -l -f /var/lib/otto-bgp/ssh-keys/known_hosts

# Add new router (requires setup mode)
OTTO_BGP_SETUP_MODE=true ssh-keyscan -H new-router.company.com >> /var/lib/otto-bgp/ssh-keys/known_hosts

# Validate host key file
otto-bgp config validate --section ssh
```

## Systemd Integration

### Service Configuration

**Service File (`/etc/systemd/system/otto-bgp.service`):**
```ini
[Unit]
Description=Otto BGP Autonomous Policy Manager
Documentation=https://docs.otto-bgp.com
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
User=otto.bgp
Group=otto.bgp
WorkingDirectory=/var/lib/otto-bgp
ExecStart=/opt/otto-bgp/venv/bin/python /opt/otto-bgp/otto_bgp/main.py pipeline /etc/otto-bgp/devices.csv --output-dir /var/lib/otto-bgp/output
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=30
TimeoutStopSec=60

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/otto-bgp /var/log/otto-bgp
CapabilityBoundingSet=CAP_NET_RAW

# Environment
Environment=OTTO_BGP_CONFIG_DIR=/etc/otto-bgp
Environment=OTTO_BGP_DATA_DIR=/var/lib/otto-bgp
Environment=OTTO_BGP_LOG_DIR=/var/log/otto-bgp
Environment=PYTHONPATH=/opt/otto-bgp

[Install]
WantedBy=multi-user.target
```

**Timer for Scheduled Operations (`/etc/systemd/system/otto-bgp.timer`):**
```ini
[Unit]
Description=Otto BGP Scheduled Policy Update
Requires=otto-bgp.service

[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
```

### Service Management

```bash
# Enable and start service
sudo systemctl enable otto-bgp.service
sudo systemctl start otto-bgp.service

# Enable scheduled execution
sudo systemctl enable otto-bgp.timer
sudo systemctl start otto-bgp.timer

# Check status
sudo systemctl status otto-bgp.service
sudo systemctl status otto-bgp.timer

# View logs
sudo journalctl -u otto-bgp.service -f
sudo journalctl -u otto-bgp.service --since "1 hour ago"

# Restart service
sudo systemctl restart otto-bgp.service

# Stop service
sudo systemctl stop otto-bgp.service
```

### Service Monitoring

```bash
# Monitor autonomous operations
sudo journalctl -u otto-bgp.service -f | grep -i "autonomous\|netconf\|commit"

# Check email notification logs
sudo journalctl -u otto-bgp.service | grep -i "email\|smtp\|notification"

# Monitor for failures
sudo journalctl -u otto-bgp.service | grep -i "error\|failed\|exception"

# Performance monitoring
sudo journalctl -u otto-bgp.service | grep -i "stage.*complete"
```

## Configuration Management

### Configuration File Locations

| Installation Mode | Configuration File | Data Directory | Log Directory |
|------------------|-------------------|----------------|---------------|
| User | `~/.config/otto-bgp/otto.env` | `~/.local/share/otto-bgp` | `~/.local/share/otto-bgp/logs` |
| System | `/etc/otto-bgp/otto.env` | `/var/lib/otto-bgp` | `/var/lib/otto-bgp/logs` |
| Autonomous | `/etc/otto-bgp/otto.env` | `/var/lib/otto-bgp` | `/var/lib/otto-bgp/logs` |

### Configuration Schema Validation

```bash
# Validate configuration
otto-bgp config validate

# Validate specific sections
otto-bgp config validate --section autonomous_mode
otto-bgp config validate --section installation_mode

# Show configuration
otto-bgp config show
otto-bgp config show --section email
```

### Environment Variable Overrides

```bash
# Override autonomous mode settings
export OTTO_BGP_AUTONOMOUS_ENABLED=true
export OTTO_BGP_AUTO_APPLY_THRESHOLD=200

# Override email settings
export OTTO_BGP_SMTP_SERVER=smtp.newserver.com
export OTTO_BGP_EMAIL_TO=newteam@company.com

# Override installation settings
export OTTO_BGP_SERVICE_USER=custom-user
export OTTO_BGP_DATA_DIR=/custom/data/dir
```

## Troubleshooting Installation

### Common Installation Issues

#### 1. Permission Errors

```bash
# Fix permission issues
sudo chown -R otto.bgp:otto.bgp /var/lib/otto-bgp
sudo chmod 750 /etc/otto-bgp
sudo chmod 700 /var/lib/otto-bgp/ssh-keys

# SSH key permissions
sudo chmod 600 /var/lib/otto-bgp/ssh-keys/*
```

#### 2. Dependency Issues

```bash
# Check Python version
python3 --version  # Must be 3.9+

# Install missing dependencies
pip install -r requirements.txt

# Check bgpq4 installation
bgpq4 -h
which bgpq4
```

#### 3. SMTP Configuration Issues

```bash
# Test SMTP connectivity
telnet smtp.company.com 587

# Test email configuration
python3 -c "
import smtplib
from email.mime.text import MIMEText
msg = MIMEText('Test message')
msg['Subject'] = 'Otto BGP Test'
msg['From'] = 'otto-bgp@company.com'
msg['To'] = 'test@company.com'
with smtplib.SMTP('smtp.company.com', 587) as server:
    server.starttls()
    server.send_message(msg)
print('Email test successful')
"
```

#### 4. Systemd Service Issues

```bash
# Check service status
sudo systemctl status otto-bgp.service

# Check service logs
sudo journalctl -u otto-bgp.service --no-pager

# Validate service file
sudo systemd-analyze verify /etc/systemd/system/otto-bgp.service

# Reload systemd configuration
sudo systemctl daemon-reload
```

### Installation Verification

```bash
# Verify installation
otto-bgp --version
otto-bgp config validate

# Test basic functionality
otto-bgp policy sample_as.txt --test

# Test discovery (if devices available)
otto-bgp discover test_devices.csv --dry-run

# Verify autonomous mode (if enabled)
otto-bgp apply --autonomous --dry-run
```

### Diagnostic Commands

```bash
# System information
otto-bgp config show --section installation_mode

# Check file permissions
ls -la /var/lib/otto-bgp/
ls -la /etc/otto-bgp/

# Check service user
id otto.bgp
sudo -u otto.bgp otto-bgp --version

# Network connectivity
ping router1.company.com
ssh otto.bgp@router1.company.com "show version"

# Log analysis
sudo tail -f /var/log/otto-bgp/otto-bgp.log
sudo grep -i error /var/log/otto-bgp/otto-bgp.log
```

## Uninstallation

Otto BGP provides built-in uninstallation support for both user and system installations.

### Quick Uninstall

**Complete removal** (removes everything):
```bash
# Interactive mode (recommended - prompts for confirmation)
curl -O https://raw.githubusercontent.com/networksandchill/otto-bgp/main/uninstall.sh
chmod +x uninstall.sh
sudo ./uninstall.sh  # Use sudo for system installations

# Non-interactive mode (requires explicit confirmation)
curl -fsSL https://raw.githubusercontent.com/networksandchill/otto-bgp/main/uninstall.sh | sudo bash -s -- --yes

# Or download and run with options
curl -O https://raw.githubusercontent.com/networksandchill/otto-bgp/main/uninstall.sh
chmod +x uninstall.sh
./uninstall.sh --help  # See all available options
```

### Selective Uninstall

The uninstall scripts provide interactive prompts to keep specific data:

**Via uninstall script (interactive):**
```bash
# The uninstall script will ask if you want to keep:
# - Configuration files
# - Data directories (SSH keys, policies, logs)
# - Service user (system installations)
curl -O https://raw.githubusercontent.com/networksandchill/otto-bgp/main/uninstall.sh
chmod +x uninstall.sh
sudo ./uninstall.sh  # Interactive prompts for selective removal
```

**Manual selective removal:**
```bash
# Download and run uninstall script with options
curl -O https://raw.githubusercontent.com/networksandchill/otto-bgp/main/uninstall.sh
chmod +x uninstall.sh
./uninstall.sh  # Interactive prompts for selective removal
```

### Manual Uninstallation

If the automated uninstall scripts are not available:

**User Installation:**
```bash
# Remove binary
rm -f ~/.local/bin/otto-bgp

# Remove libraries
rm -rf ~/.local/lib/otto-bgp

# Remove configuration (optional)
rm -rf ~/.local/etc/otto-bgp

# Remove data (optional - contains SSH keys and policies)
rm -rf ~/.local/share/otto-bgp
```

**System Installation:**
```bash
# Stop and disable service
sudo systemctl stop otto-bgp.timer otto-bgp.service
sudo systemctl disable otto-bgp.timer otto-bgp.service

# Remove systemd files
sudo rm -f /etc/systemd/system/otto-bgp.service
sudo rm -f /etc/systemd/system/otto-bgp.timer
sudo systemctl daemon-reload

# Remove binary and libraries
sudo rm -f /usr/local/bin/otto-bgp
sudo rm -rf /opt/otto-bgp

# Remove configuration (optional)
sudo rm -rf /etc/otto-bgp

# Remove data (optional - contains SSH keys and policies)
sudo rm -rf /var/lib/otto-bgp

# Remove service user (optional)
sudo userdel otto-bgp
```

### Data Backup Before Uninstall

**Backup important data:**
```bash
# User installation
mkdir ~/otto-bgp-backup
cp -r ~/.local/etc/otto-bgp ~/otto-bgp-backup/config 2>/dev/null || true
cp -r ~/.local/share/otto-bgp/ssh-keys ~/otto-bgp-backup/ssh-keys 2>/dev/null || true
cp -r ~/.local/share/otto-bgp/policies ~/otto-bgp-backup/policies 2>/dev/null || true

# System installation
sudo mkdir /tmp/otto-bgp-backup
sudo cp -r /etc/otto-bgp /tmp/otto-bgp-backup/config 2>/dev/null || true
sudo cp -r /var/lib/otto-bgp/ssh-keys /tmp/otto-bgp-backup/ssh-keys 2>/dev/null || true
sudo cp -r /var/lib/otto-bgp/policies /tmp/otto-bgp-backup/policies 2>/dev/null || true
sudo chown -R $USER:$USER /tmp/otto-bgp-backup
```

### Clean Uninstall Script

```bash
#!/bin/bash
# uninstall-otto-bgp.sh

echo "Otto BGP Uninstallation"
echo "======================="

# Detect installation mode
if [[ -d "/opt/otto-bgp" ]]; then
    echo "Detected system installation"
    
    # Stop services
    sudo systemctl stop otto-bgp.service otto-bgp.timer 2>/dev/null || true
    sudo systemctl disable otto-bgp.service otto-bgp.timer 2>/dev/null || true
    
    # Remove files
    sudo rm -rf /opt/otto-bgp/
    sudo rm -rf /etc/otto-bgp/
    sudo rm -rf /var/lib/otto-bgp/
    sudo rm -rf /var/log/otto-bgp/
    sudo rm -f /etc/systemd/system/otto-bgp.*
    
    # Remove user
    sudo userdel otto.bgp 2>/dev/null || true
    
    echo "System installation removed"
    
elif [[ -f "$HOME/.local/bin/otto-bgp" ]]; then
    echo "Detected user installation"
    
    # Remove user files
    rm -f ~/.local/bin/otto-bgp
    rm -rf ~/.otto-bgp/
    
    echo "User installation removed"
else
    echo "No Otto BGP installation found"
fi

echo "Uninstallation complete"
```

## Troubleshooting

### Common Issues

#### 1. SSH Connection Failures

For comprehensive SSH troubleshooting, see the SSH Host Key Management section in the Network Engineering Reference guide.

**Quick Diagnostics:**
```bash
# Check service logs for SSH errors
sudo journalctl -u otto-bgp.service | grep -i ssh

# Test SSH connectivity manually
sudo -u otto-bgp ssh -i /var/lib/otto-bgp/ssh-keys/otto-bgp bgp-read@192.168.1.1

# Check SSH key permissions
ls -la /var/lib/otto-bgp/ssh-keys/
```

**Common Solutions:**
- **Host Key Mismatch**: See Network Engineering Reference for device replacement/upgrade procedures
- **New Device**: See Network Engineering Reference for adding devices to the system
- **Permission Issues**: Check file ownership and SSH key permissions (see below)
- **Network Issues**: Verify firewall rules and device accessibility

#### 2. BGPq4 Issues  
```bash
# Test bgpq4 manually
bgpq4 -Jl 13335 AS13335

# Check network connectivity
curl -I https://bgp.tools/

# Test with Podman fallback
./otto-bgp --dev policy sample_input.txt --test
```

**RHEL-based Systems (EPEL Issues):**
```bash
# Check if EPEL repository is enabled
dnf repolist enabled | grep epel
# OR for older systems:
yum repolist enabled | grep epel

# If EPEL is not enabled, install it:
sudo dnf install -y epel-release

# Verify bgpq4 is available in EPEL
dnf search bgpq4

# If bgpq4 is still not found, try refreshing metadata:
sudo dnf clean all
sudo dnf makecache

# Install bgpq4 from EPEL
sudo dnf install -y bgpq4
```

**Common EPEL-related Issues:**
- **"No package bgpq4 available"**: EPEL repository not enabled or not properly configured
- **"Repository epel is listed more than once"**: Multiple EPEL repository definitions, clean up with `dnf config-manager --disable epel` then reinstall
- **"EPEL repository is not available"**: Check network connectivity and DNS resolution

#### 3. Permission Issues
```bash
# Fix ownership
sudo chown -R otto-bgp:otto-bgp /var/lib/otto-bgp
sudo chown otto-bgp:otto-bgp /opt/otto-bgp

# Check systemd service permissions
sudo systemctl show otto-bgp.service | grep "^User\|^Group"
```

#### 4. Configuration Issues
```bash
# Validate configuration
sudo -u otto-bgp /var/lib/otto-bgp/venv/bin/python -c "
from otto-bgp.utils.config import get_config_manager
cm = get_config_manager()
issues = cm.validate_config()
if issues:
    for issue in issues: print(f'Config issue: {issue}')
else:
    print('Configuration is valid')
"
```

#### 5. Autonomous Mode Issues

**Configuration Problems:**
```bash
# Check autonomous mode configuration
./otto-bgp config show | grep -A 10 autonomous_mode

# Verify autonomous mode is enabled
./otto-bgp config validate

# Test email notifications
./otto-bgp test-email-notifications
```

**Email Notification Failures:**
```bash
# Check email configuration
sudo journalctl -u otto-bgp.service | grep -i email

# Test SMTP connectivity
telnet smtp.company.com 587

# Verify email credentials
./otto-bgp config show | grep -A 5 "notifications"
```

**Autonomous Decision Issues:**
```bash
# Check safety validation logs
sudo journalctl -u otto-bgp.service | grep -i "autonomous\|risk\|threshold"

# Review autonomous decisions
cat /var/lib/otto-bgp/logs/autonomous-decisions.log

# Verify threshold settings (informational only)
./otto-bgp config show | grep auto_apply_threshold
```

**NETCONF Event Monitoring:**
```bash
# Monitor all NETCONF events
sudo journalctl -u otto-bgp.service | grep -i "netconf\|commit\|connect"

# Check router connectivity
./otto-bgp test-router-connection device.csv

# Verify safety overrides
./otto-bgp config show | grep -A 5 safety_overrides
```

### Debug Mode
```bash
# Run with verbose logging
sudo -u otto-bgp /opt/otto-bgp/otto-bgp -v policy sample_input.txt --test

# Check all logs
sudo journalctl -u otto-bgp.service --no-pager | grep -E "(ERROR|WARN|Failed)"
```

### Log Files
- **Service Logs**: `journalctl -u otto-bgp.service`
- **Application Logs**: `/var/lib/otto-bgp/logs/otto-bgp.log`
- **System Logs**: `/var/log/syslog` (otto-bgp entries)

### Support Resources
- **Configuration**: Check `/etc/otto-bgp/otto.env` (system) or `~/.config/otto-bgp/otto.env` (user)
- **Environment**: Check installation-specific otto.env file
- **Dependencies**: Ensure bgpq4, Python 3.9+, and paramiko are installed
- **Network**: Verify SSH access to devices and internet connectivity for bgpq4
- **Autonomous Mode**: Check email configuration and SMTP connectivity
- **NETCONF Events**: Monitor systemd logs for complete audit trail

## Best Practices

### Installation Recommendations

1. **Start with User Mode**: Test functionality before system installation
2. **System Mode for Production**: Use system mode for production environments
3. **Autonomous Mode Planning**: Carefully plan autonomous mode deployment
4. **Backup Configurations**: Backup router configurations before deployment
5. **Monitor Email Notifications**: Ensure email delivery for autonomous operations

### Security Considerations

1. **SSH Key Management**: Use dedicated SSH keys for Otto BGP
2. **Service User**: Never run as root in production
3. **File Permissions**: Maintain strict file permissions
4. **Host Key Verification**: Always use strict host key checking
5. **Email Security**: Use TLS for SMTP connections

### Operational Guidelines

1. **Testing**: Always test in lab environment first
2. **Monitoring**: Set up log monitoring and alerting
3. **Backup Strategy**: Maintain configuration and data backups
4. **Update Process**: Plan for Otto BGP updates
5. **Documentation**: Document your specific configuration and procedures

This installation guide provides comprehensive coverage of all Otto BGP v0.3.2 installation modes and operational requirements.