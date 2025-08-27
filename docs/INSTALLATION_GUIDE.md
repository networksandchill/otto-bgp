# Otto BGP Installation Guide

## Overview

Otto BGP v0.3.2 provides a two-mode installation system with optional autonomous operation for system installations. This guide provides accurate, step-by-step installation instructions based on the actual implementation.

**Installation Philosophy**: Clear separation between installation modes and operational capabilities with mandatory safety confirmation for autonomous features.

## Installation System

### Installation Modes

| Mode | Target Use | Installation Scope | Autonomous Support | Safety Level |
|------|------------|-------------------|-------------------|--------------|
| **User** | Development/Testing | Local user directory (`~/.local/`) | ❌ | Basic |
| **System** | Production | System-wide (`/usr/local/`, `/etc/`, `/var/lib/`) | ✅ Optional | Enhanced |

### Mode Comparison

```
┌─────────────────────────────────────────────────────────────────┐
│                 Otto BGP Installation Modes                     │
├─────────────────┬───────────────────────────────────────────────┤
│   USER MODE     │            SYSTEM MODE                       │
│                 │                                               │
│ • Local install │ • System-wide installation                   │
│ • Dev/testing   │ • Production deployment                      │
│ • Basic safety  │ • Enhanced safety features                   │
│ • Manual only   │ • Optional autonomous operation              │
│                 │ • SystemD integration                       │
│                 │ • Service user isolation                     │
└─────────────────┴───────────────────────────────────────────────┘
```

## Prerequisites

### System Requirements

**Minimum Requirements:**
- Linux/macOS operating system
- Python 3.10+ with pip
- SSH client
- 1GB free disk space

**System Installation Requirements:**
- systemd-based Linux distribution (for service integration)
- sudo/root access for system installation
- Dedicated service user (automatically created)
- SMTP server for email notifications (autonomous mode only)
- 2GB+ free disk space

### Dependencies

**Core Dependencies:**
```bash
# Python packages (automatically installed by install.sh)
# junos-eznc - Juniper device automation
# paramiko - SSH client library
# PyYAML - YAML configuration parsing
# pandas - Data processing (optional)

# System packages (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv git openssh-client curl

# System packages (RHEL/CentOS)
sudo dnf install -y python3 python3-pip python3-venv git openssh-clients curl

# bgpq4 (required for policy generation)
# Debian/Ubuntu: sudo apt install bgpq4
# RHEL/CentOS/Rocky Linux: sudo dnf install epel-release && sudo dnf install bgpq4
# Or use containerized version with Docker/Podman

# rpki-client (optional but recommended for RPKI validation)
# Debian/Ubuntu: sudo apt install rpki-client
# RHEL/CentOS/Rocky Linux: sudo dnf install epel-release && sudo dnf install rpki-client
# FreeBSD: pkg install rpki-client
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
- Installs binary to `~/.local/bin/otto-bgp`
- Installs libraries to `~/.local/lib/otto-bgp`
- Creates configuration in `~/.config/otto-bgp/`
- Creates data directory in `~/.local/share/otto-bgp/`
- Creates virtual environment at `~/.local/venv`
- No system modifications
- Basic safety controls only

**Configuration created:**

Configuration is created from `systemd/otto.env.user` template with actual username substituted:

```bash
# ~/.config/otto-bgp/otto.env (key settings shown)
OTTO_BGP_ENVIRONMENT=user
OTTO_BGP_INSTALLATION_MODE=user
OTTO_BGP_SERVICE_USER=actual_username
OTTO_BGP_SYSTEMD_ENABLED=false
OTTO_BGP_AUTONOMOUS_ENABLED=false
OTTO_BGP_AUTO_APPLY_ENABLED=false
OTTO_BGP_DRY_RUN_MODE=true
```

#### 2. System Mode Installation

**Purpose**: Production deployment with enhanced safety controls

```bash
./install.sh --system
```

**What it does:**
- Installs binary to `/usr/local/bin/otto-bgp`
- Installs libraries to `/usr/local/lib/otto-bgp`
- Creates configuration in `/etc/otto-bgp/`
- Creates data directories in `/var/lib/otto-bgp/{ssh-keys,logs,cache,policies}`
- Creates virtual environment at `/usr/local/venv`
- Creates service user `otto-bgp`
- Sets up systemd service file
- Sets up systemd timer (for non-autonomous mode)
- Enhanced security and performance hardening
- Autonomous mode available but disabled by default

**System Setup:**
```bash
# Creates service user (hyphen naming)
sudo useradd -r -s /bin/false -d /var/lib/otto-bgp otto-bgp

# Creates directories
sudo mkdir -p /etc/otto-bgp
sudo mkdir -p /var/lib/otto-bgp/{policies,logs,ssh-keys}
sudo mkdir -p /var/log/otto-bgp

# Sets permissions
sudo chown -R otto-bgp:otto-bgp /var/lib/otto-bgp
sudo chown -R otto-bgp:otto-bgp /var/log/otto-bgp
sudo chmod 750 /etc/otto-bgp
sudo chmod 700 /var/lib/otto-bgp/ssh-keys
```

**Configuration created:**

Configuration is created from `systemd/otto.env.system` template:

```bash
# /etc/otto-bgp/otto.env (key settings shown)
OTTO_BGP_ENVIRONMENT=system
OTTO_BGP_INSTALLATION_MODE=system
OTTO_BGP_SERVICE_USER=otto-bgp
OTTO_BGP_SYSTEMD_ENABLED=true
OTTO_BGP_OPTIMIZATION_LEVEL=enhanced
OTTO_BGP_AUTONOMOUS_ENABLED=false
OTTO_BGP_AUTO_APPLY_ENABLED=false
OTTO_BGP_DRY_RUN_MODE=false
OTTO_BGP_STRICT_HOST_KEY_CHECKING=true
```

#### 3. Autonomous Mode Configuration

**Purpose**: Hands-off operations with automatic policy application

**Note**: Autonomous mode is a configuration flag for system installations, not a separate installation mode.

**⚠️ Interactive Setup Required:**
Autonomous mode setup requires interactive configuration and cannot be done through piped installation.

```bash
# Download and run locally (required for autonomous mode)
curl -O https://raw.githubusercontent.com/networksandchill/otto-bgp/main/install.sh
chmod +x install.sh
./install.sh --autonomous
```

**⚠️ Critical Safety Warning:**
This mode enables automatic policy application. Mandatory safety confirmation required.

**Interactive Setup Process:**
The install.sh script will prompt for:
- Risk acknowledgment (must type 'confirm')
- Auto-apply threshold (informational only)
- SMTP server configuration
- Email notification settings
- Engineer notification recipients

**Configuration Result:**

After autonomous setup, configuration is created from `systemd/otto.env.autonomous` template:

```bash
# /etc/otto-bgp/otto.env (autonomous mode)
OTTO_BGP_ENVIRONMENT=system
OTTO_BGP_INSTALLATION_MODE=system
OTTO_BGP_SERVICE_USER=otto-bgp
OTTO_BGP_SYSTEMD_ENABLED=true
OTTO_BGP_AUTONOMOUS_ENABLED=true
# SMTP settings populated from interactive setup
OTTO_BGP_SMTP_SERVER=smtp.company.com
OTTO_BGP_SMTP_PORT=587
OTTO_BGP_SMTP_USE_TLS=true
OTTO_BGP_FROM_ADDRESS=otto-bgp@company.com
```

**Note**: Email recipients must be configured in `/etc/otto-bgp/config.json` as they cannot be set via environment variables. See Configuration Management section below for details.

## Installation Script Reference

### install.sh Command Line Options

```bash
./install.sh [OPTIONS]

OPTIONS:
  --user               Install in user mode (default)
  --system             Install in system mode for production
  --autonomous         Install with autonomous mode (requires interactive prompts)
  --skip-bgpq4         Skip bgpq4 dependency check
  --force              Force installation (overwrite existing installation)
  --help, -h           Show help message
```

### Installation Process Flow (as implemented in install.sh v0.3.2)

```text
1) Check Python version (requires 3.10+)
2) Check requirements (git, curl, bgpq4/docker/podman if not skipped)
3) (If autonomous) Run interactive autonomous configuration prompts
4) Check for existing installation (remove if --force)
5) Create directories (bin, lib, config, data)
6) Download repo contents into lib dir
7) Create virtual environment and install Python dependencies
8) Create CLI wrapper at <bin>/otto-bgp
9) Create environment config from template into <config>/otto.env
10) Create systemd service (+ timer when not autonomous) in system mode
11) Print next steps and enable guidance
```

## Manual Production Deployment

For environments requiring manual installation or custom configurations, follow these detailed production deployment steps.

Note: install.sh installs to `/usr/local` for system mode by default. The steps below have been aligned to those locations to avoid path mismatches.

### Production System Requirements

**Operating System**: Debian 12 (Bookworm) or Ubuntu 22.04+
**Hardware**: 4 vCPU, 8GB RAM, 100GB storage
**Network**: Outbound HTTPS (bgpq4 queries), SSH to target devices

### IRR Proxy Compatibility

- Proxy support requires native `bgpq4` (host binary). Docker/Podman modes do not work with SSH tunnels because container `127.0.0.1` cannot reach host-bound tunnel ports.
- Proxy + parallel generation: Parallel policy generation IS supported with proxy via tunnel snapshotting. Worker count is automatically capped to 4 when proxy is active. Use `OTTO_BGP_BGPQ4_MAX_WORKERS=N` to set specific worker count if needed.
- Validate the proxy setup with: `otto-bgp test-proxy --test-bgpq4`.
- Ensure a dedicated SSH key and `known_hosts` for the jump host are present and readable by the `otto-bgp` user.

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

# Enable EPEL repository (required for bgpq4 and rpki-client)
sudo dnf install -y epel-release

# Install dependencies
sudo dnf install -y python3 python3-pip python3-venv git openssh-clients systemd podman

# Install bgpq4 from EPEL
sudo dnf install -y bgpq4

# Install rpki-client from EPEL (recommended for RPKI validation)
sudo dnf install -y rpki-client

# Verify installations
bgpq4 --help
rpki-client --help
which bgpq4  # Should show /usr/bin/bgpq4
which rpki-client  # Should show /usr/bin/rpki-client
```

**Note:** The Otto BGP installation script will automatically handle EPEL repository setup for RHEL-based systems when needed.

#### 2. User and Directory Setup
```bash
# Create dedicated system user
sudo useradd --system --shell /bin/false --home /var/lib/otto-bgp \
    --create-home otto-bgp

# Create directory structure
sudo mkdir -p /usr/local/lib/otto-bgp
sudo mkdir -p /var/lib/otto-bgp/{logs,policies,ssh-keys}
sudo mkdir -p /etc/otto-bgp

# Set ownership
sudo chown -R otto-bgp:otto-bgp /var/lib/otto-bgp
sudo chown otto-bgp:otto-bgp /usr/local/lib/otto-bgp
```

#### 3. Application Deployment
```bash
# Clone repository
sudo git clone https://github.com/networksandchill/otto-bgp.git /usr/local/lib/otto-bgp
cd /usr/local/lib/otto-bgp

# Create virtual environment
sudo python3 -m venv /usr/local/venv

# Install dependencies
sudo /usr/local/venv/bin/pip install -r requirements.txt

# Create CLI wrapper
sudo tee /usr/local/bin/otto-bgp >/dev/null <<'EOF'
#!/bin/bash
VENV_PYTHON="/usr/local/venv/bin/python"
export OTTO_BGP_CONFIG_DIR="/etc/otto-bgp"
export OTTO_BGP_DATA_DIR="/var/lib/otto-bgp"
if [[ -f "$OTTO_BGP_CONFIG_DIR/otto.env" ]]; then
  source "$OTTO_BGP_CONFIG_DIR/otto.env"
fi
cd "/usr/local/lib/otto-bgp"
exec "$VENV_PYTHON" -m otto_bgp.main "$@"
EOF
sudo chmod +x /usr/local/bin/otto-bgp
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
sudo chmod +x /usr/local/lib/otto-bgp/scripts/setup-host-keys.sh
sudo /usr/local/lib/otto-bgp/scripts/setup-host-keys.sh \
    /etc/otto-bgp/devices.csv \
    /var/lib/otto-bgp/ssh-keys/known_hosts

# Method 2: Use Python setup script with Otto
sudo /usr/local/venv/bin/python \
    /usr/local/lib/otto-bgp/scripts/setup_host_keys.py \
    --devices /etc/otto-bgp/devices.csv \
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
sudo cp /usr/local/lib/otto-bgp/systemd/otto.env.system /etc/otto-bgp/otto.env

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
sudo tee /etc/otto-bgp/devices.csv << 'EOF'
address,hostname
192.168.1.1,core-router-1
192.168.1.2,core-router-2  
10.0.1.10,edge-router-1
EOF

# Set ownership
sudo chown otto-bgp:otto-bgp /etc/otto-bgp/devices.csv
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
chown otto-bgp:otto-bgp "$KNOWN_HOSTS_FILE"

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

# Validate known_hosts entries for a router (example)
ssh-keygen -F new-router.company.com -f /var/lib/otto-bgp/ssh-keys/known_hosts || true
```

## Systemd Integration

### Service Configuration

**Service File (`/etc/systemd/system/otto-bgp.service` generated by install.sh):**
```ini
[Unit]
Description=Otto BGP v0.3.2 - Orchestrated Transit Traffic Optimizer
Documentation=file:///usr/local/lib/otto-bgp/README.md
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=otto-bgp
Group=otto-bgp
WorkingDirectory=/usr/local/lib/otto-bgp
ExecStart=/usr/local/bin/otto-bgp pipeline /etc/otto-bgp/devices.csv --output-dir /var/lib/otto-bgp/policies
Environment=PYTHONPATH=/usr/local/lib/otto-bgp
EnvironmentFile=-/etc/otto-bgp/otto.env

# Security hardening
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

# Directory access
ReadWritePaths=/var/lib/otto-bgp/policies
ReadWritePaths=/var/lib/otto-bgp/logs
ReadOnlyPaths=/etc/otto-bgp
ReadOnlyPaths=/usr/local/lib/otto-bgp

# Logging and limits
StandardOutput=journal
StandardError=journal
SyslogIdentifier=otto-bgp
TimeoutStartSec=300
TimeoutStopSec=60
MemoryMax=1G
CPUQuota=50%

[Install]
WantedBy=multi-user.target
```

**Timer for Scheduled Operations (`/etc/systemd/system/otto-bgp.timer` when not in autonomous mode):**
```ini
[Unit]
Description=Otto BGP v0.3.2 Scheduled Policy Update
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

Otto BGP uses a dual configuration system combining environment variables with optional JSON configuration for complex settings.

### Configuration File Locations

| Installation Mode | Environment Config | JSON Config (Optional) | Data Directory | Log Directory |
|------------------|-------------------|----------------------|----------------|---------------|
| User | `~/.config/otto-bgp/otto.env` | `~/.config/otto-bgp/config.json` | `~/.local/share/otto-bgp` | `~/.local/share/otto-bgp/logs` |
| System | `/etc/otto-bgp/otto.env` | `/etc/otto-bgp/config.json` | `/var/lib/otto-bgp` | `/var/lib/otto-bgp/logs` |
| Autonomous | `/etc/otto-bgp/otto.env` | `/etc/otto-bgp/config.json` | `/var/lib/otto-bgp` | `/var/lib/otto-bgp/logs` |

### Configuration System Overview

Otto BGP uses a **two-layer configuration system**:

1. **Environment Variables** (otto.env) - Primary configuration for simple settings ✅ **REQUIRED**
2. **JSON Configuration** (config.json) - Advanced configuration for complex/array settings ⚠️ **OPTIONAL**

**Loading Priority**: Environment variables **override** JSON configuration values when both are present.

### When Do You Need config.json?

**✅ config.json is NOT needed for:**
- Basic policy generation (`otto-bgp policy input.txt`)
- SSH connections to routers 
- Standard BGPq4 operations
- Basic logging and output
- System/user mode installation

**⚠️ config.json IS needed for:**
- **IRR Proxy** - Complex tunnel configurations
- **Email Recipients** - Arrays of notification addresses for autonomous mode
- **Custom Output Structure** - Router-aware directory layouts
- **AS Processing Arrays** - Custom string removal patterns
- **RPKI VRP Sources** - Multiple validation source configurations

**Rule of thumb**: Start without config.json. Add it only when you need these specific advanced features.

### Environment Variables (otto.env)

Most Otto BGP settings can be configured using environment variables in the otto.env file. These are simple KEY=value pairs that work for basic configuration:

```bash
# SSH Configuration
SSH_USERNAME=bgp-read
OTTO_BGP_SSH_PRIVATE_KEY=/var/lib/otto-bgp/ssh-keys/otto-bgp
OTTO_BGP_SSH_KNOWN_HOSTS=/var/lib/otto-bgp/ssh-keys/known_hosts
OTTO_BGP_SSH_CONNECTION_TIMEOUT=30

# BGPq4 Configuration
OTTO_BGP_BGPQ4_MODE=auto
OTTO_BGP_BGPQ4_TIMEOUT=45

# Logging Configuration
OTTO_BGP_LOG_LEVEL=INFO
OTTO_BGP_LOG_FILE=/var/lib/otto-bgp/logs/otto-bgp.log

# Autonomous Mode (Basic Settings)
OTTO_BGP_AUTONOMOUS_ENABLED=false
OTTO_BGP_AUTO_APPLY_THRESHOLD=100
OTTO_BGP_REQUIRE_CONFIRMATION=true

# Email Configuration (Basic Settings)
OTTO_BGP_EMAIL_ENABLED=true
OTTO_BGP_SMTP_SERVER=smtp.company.com
OTTO_BGP_SMTP_PORT=587
OTTO_BGP_SMTP_USE_TLS=true
OTTO_BGP_FROM_ADDRESS=otto-bgp@company.com
```

### JSON Configuration (config.json) - Advanced Settings

**Template Location**: A complete `config.json.example` template is provided in `example-configs/config.json.example`

**When to create config.json**: You need to create a config.json file when you require any of the following advanced configurations that cannot be set via environment variables.

#### Settings That REQUIRE config.json

**1. IRR Proxy Tunnels** (Most Common)
```json
{
  "irr_proxy": {
    "enabled": true,
    "jump_host": "gateway.company.com",
    "jump_user": "otto",
    "ssh_key_file": "/var/lib/otto-bgp/ssh-keys/proxy-key",
    "known_hosts_file": "/var/lib/otto-bgp/ssh-keys/proxy-known-hosts",
    "tunnels": [
      {
        "name": "whois-radb",
        "local_port": 43001,
        "remote_host": "whois.radb.net",
        "remote_port": 43
      },
      {
        "name": "whois-ripe",
        "local_port": 43002,
        "remote_host": "whois.ripe.net",
        "remote_port": 43
      }
    ]
  }
}
```

**2. Email Recipients (Autonomous Mode)**
```json
{
  "autonomous_mode": {
    "notifications": {
      "email": {
        "to_addresses": ["network-team@company.com", "ops@company.com"],
        "cc_addresses": ["manager@company.com"],
        "subject_prefix": "[Otto BGP Autonomous]"
      }
    }
  }
}
```

**3. Custom Output Directory Structure**
```json
{
  "output": {
    "router_aware_structure": true,
    "policies_subdir": "policies/routers",
    "discovery_subdir": "discovery",
    "bgp_data_filename": "bgp.txt",
    "bgp_juniper_filename": "bgp-juniper.txt",
    "create_timestamps": true,
    "backup_legacy_files": true
  }
}
```

**4. AS Processing Customization**
```json
{
  "as_processing": {
    "min_as_number": 256,
    "max_as_number": 4294967295,
    "strict_validation": true,
    "warn_reserved_ranges": true,
    "remove_substrings": ["    peer-as ", ";"]
  }
}
```

**5. RPKI VRP Sources**
```json
{
  "rpki": {
    "enabled": true,
    "vrp_sources": ["ripe", "arin", "apnic"],
    "fail_closed": true,
    "max_cache_age": 86400
  }
}
```

### Using the Complete Template

Instead of creating JSON snippets from scratch, **use the provided template**:

```bash
# View the complete template (all features included)
cat example-configs/config.json.example

# Copy and customize for your needs
sudo cp /usr/local/lib/otto-bgp/example-configs/config.json.example /etc/otto-bgp/config.json
```

**The template includes all available settings:**
- Complete IRR proxy configuration with example tunnels
- Full autonomous mode settings including email notifications  
- Custom output directory structures
- AS processing customizations
- RPKI configuration options
- SSH, BGPq4, and logging settings

**Customization approach:**
1. Copy the template to your config directory
2. Enable only the sections you need (set `"enabled": true`)
3. Customize the settings within those sections
4. Leave unused sections disabled or remove them entirely

### Creating config.json

**config.json is OPTIONAL** - Otto BGP works with only `otto.env` for basic functionality. Only create `config.json` when you need the advanced features listed above.

**System Installation:**
```bash
# Copy and customize the provided template
sudo cp /usr/local/lib/otto-bgp/example-configs/config.json.example /etc/otto-bgp/config.json

# Set proper permissions
sudo chown otto-bgp:otto-bgp /etc/otto-bgp/config.json
sudo chmod 640 /etc/otto-bgp/config.json

# Edit to customize your settings
sudo nano /etc/otto-bgp/config.json
```

**User Installation:**
```bash
# Copy and customize the provided template
cp ~/.local/lib/otto-bgp/example-configs/config.json.example ~/.config/otto-bgp/config.json

# Edit to customize your settings
nano ~/.config/otto-bgp/config.json
```

### Configuration Schema Validation

The CLI does not currently include `config` subcommands. Review or edit the environment file directly (`/etc/otto-bgp/otto.env` or `~/.config/otto-bgp/otto.env`). For advanced configuration, create `/etc/otto-bgp/config.json` and populate the JSON structure shown in this guide; the application will load it automatically when present.

### Environment Variable Overrides

```bash
# Autonomous mode
export OTTO_BGP_AUTONOMOUS_ENABLED=true
export OTTO_BGP_AUTO_THRESHOLD=200   # Informational threshold used in notifications

# Email (via environment)
export OTTO_BGP_SMTP_SERVER=smtp.newserver.com
export OTTO_BGP_SMTP_PORT=587
export OTTO_BGP_FROM_ADDRESS=otto-bgp@company.com
# Note: recipients are not read from env; see Known Gaps for how to set recipients

# Installation (read by application config, not the installer)
export OTTO_BGP_SERVICE_USER=custom-user
export OTTO_BGP_DATA_DIR=/custom/data/dir
```

## Troubleshooting Installation

### Common Installation Issues

#### 1. Permission Errors

```bash
# Fix permission issues
sudo chown -R otto-bgp:otto-bgp /var/lib/otto-bgp
sudo chmod 750 /etc/otto-bgp
sudo chmod 700 /var/lib/otto-bgp/ssh-keys

# SSH key permissions
sudo chmod 600 /var/lib/otto-bgp/ssh-keys/*
```

#### 2. Dependency Issues

```bash
# Check Python version
python3 --version  # Must be 3.10+

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

# Test basic functionality
otto-bgp policy sample_input.txt --test

# Test discovery (if devices available)
otto-bgp discover test_devices.csv --show-diff

# Preview application on a router (dry run)
otto-bgp apply --router 192.0.2.1 --policy-dir policies --dry-run
```

### Diagnostic Commands

```bash
# Check configuration and permissions
ls -la /etc/otto-bgp/
cat /etc/otto-bgp/otto.env | sed -n '1,80p'
ls -la /var/lib/otto-bgp/

# Check service user
id otto-bgp
sudo -u otto-bgp otto-bgp --version

# Network connectivity
ping -c1 router1.company.com
ssh otto-bgp@router1.company.com "show version" || true

# Journal log analysis
sudo journalctl -u otto-bgp.service --no-pager | tail -n 100
sudo journalctl -u otto-bgp.service | grep -i error | tail -n 50
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

# Remove binary, libraries, and virtual environment
sudo rm -f /usr/local/bin/otto-bgp
sudo rm -rf /usr/local/lib/otto-bgp
sudo rm -rf /usr/local/venv

# Remove configuration (optional)
sudo rm -rf /etc/otto-bgp

# Remove data (optional - contains SSH keys and policies)
sudo rm -rf /var/lib/otto-bgp

# Remove service user (optional)
sudo userdel otto-bgp
```

## Known Gaps and Limitations

- Systemd service: install.sh generates a oneshot service that runs the unified pipeline and, when not in autonomous mode, a daily timer. Earlier examples with Type=notify, ExecReload, and different paths are outdated and have been replaced with the exact service shape created by install.sh.
- Directory locations: install.sh installs into `/usr/local/bin`, `/usr/local/lib/otto-bgp`, and `/usr/local/venv` for system mode; and into `~/.local/bin`, `~/.local/lib/otto-bgp`, and `~/.local/venv` for user mode. Any references to `/opt/otto-bgp` are for manual deployment and are not used by the installer.
- Config CLI: There is no `otto-bgp config ...` CLI at this time. Prior references to `otto-bgp config show/validate` were removed. Edit `/etc/otto-bgp/otto.env` directly or create `/etc/otto-bgp/config.json` for advanced settings (see Configuration Management section above for complete documentation).
- Email recipients in autonomous mode: Must be configured in `/etc/otto-bgp/config.json` under `autonomous_mode.notifications.email.to_addresses` as they cannot be set via environment variables. Without a JSON config, recipients default to `["network-engineers@company.com"]`. Use the provided `example-configs/config.json.example` template.
- bgpq4 configuration via env: Runtime selection of bgpq4 is done via CLI and auto‑detection (native, docker, podman). The code does not read `OTTO_BGP_BGPQ4_*` environment variables. Ensure native `bgpq4` or Docker/Podman is available; use `otto-bgp policy --test` to verify.
- Devices file: The systemd service expects `/etc/otto-bgp/devices.csv` to exist. The installer does not create this file; you must supply it.
- Configuration management: Some documentation refers to configuration validation CLI commands that don't exist. Configuration validation is done at runtime, not via CLI.
- Dependencies: Code uses bgpq4 (not bgpq3) and actual requirements.txt contains only 4 packages: junos-eznc, paramiko, PyYAML, pandas.
- Autonomous mode: Not a separate installation mode but a configuration flag (`AUTONOMOUS_MODE=true`) applied to system installations.

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

### Manual Uninstall (if uninstall.sh unavailable)

**Note**: Use the provided `uninstall.sh` script when possible. The manual steps below are for reference only.

```bash
#!/bin/bash
# Manual uninstall steps (use uninstall.sh instead)

echo "Otto BGP Manual Uninstallation"
echo "=============================="

# Detect installation mode
if [[ -d "/usr/local/lib/otto-bgp" ]]; then
    echo "Detected system installation"
    
    # Stop services
    sudo systemctl stop otto-bgp.service otto-bgp.timer 2>/dev/null || true
    sudo systemctl disable otto-bgp.service otto-bgp.timer 2>/dev/null || true
    
    # Remove files
    sudo rm -rf /usr/local/lib/otto-bgp/
    sudo rm -rf /usr/local/venv/
    sudo rm -f /usr/local/bin/otto-bgp
    sudo rm -rf /etc/otto-bgp/
    sudo rm -rf /var/lib/otto-bgp/
    sudo rm -f /etc/systemd/system/otto-bgp.*
    
    # Remove user
    sudo userdel otto-bgp 2>/dev/null || true
    
    echo "System installation removed"
    
elif [[ -f "$HOME/.local/bin/otto-bgp" ]]; then
    echo "Detected user installation"
    
    # Remove user files
    rm -f ~/.local/bin/otto-bgp
    rm -rf ~/.local/lib/otto-bgp/
    rm -rf ~/.local/venv/
    rm -rf ~/.config/otto-bgp/
    rm -rf ~/.local/share/otto-bgp/
    
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

# Test bgpq4 via IRR proxy (native bgpq4 only)
otto-bgp test-proxy --test-bgpq4

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
- **Dependencies**: Ensure bgpq4, Python 3.10+, and paramiko are installed
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
