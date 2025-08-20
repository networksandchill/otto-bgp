# Otto BGP SystemD Service Files

This directory contains SystemD service and timer configurations for Otto BGP production deployment with dual-service architecture.

## Files

- **otto-bgp.service**: System mode service (manual operations with lightweight hardening)
- **otto-bgp.timer**: Timer for system mode scheduled execution
- **otto-bgp-autonomous.service**: Autonomous mode service (enhanced security hardening)
- **otto-bgp-autonomous.timer**: Timer for autonomous mode scheduled execution
- **otto-bgp-rpki-preflight.service**: RPKI VRP freshness validation (blocks autonomous mode if stale)
- **otto.env.user**: User installation environment template
- **otto.env.system**: System installation environment template  
- **otto.env.autonomous**: Autonomous mode environment template
- **README.md**: This documentation file

## Dual-Service Architecture

Otto BGP implements a dual-service architecture for different operational modes:

### System Mode (otto-bgp.service)
- **Purpose**: Manual operations, interactive use, initial deployment
- **Security**: Lightweight hardening, full network access
- **Resources**: Higher limits (2GB RAM, 75% CPU)
- **Scheduling**: Optional via otto-bgp.timer

### Autonomous Mode (otto-bgp-autonomous.service)  
- **Purpose**: Scheduled autonomous operations, production automation
- **Security**: Enhanced hardening, network isolation, strict sandboxing
- **Resources**: Constrained limits (1GB RAM, 25% CPU)
- **Scheduling**: Via otto-bgp-autonomous.timer (every 4 hours)
- **Dependencies**: Requires RPKI preflight check

## Installation

### 1. Copy Service Files

```bash
# Copy all service and timer files
sudo cp systemd/otto-bgp.service /etc/systemd/system/
sudo cp systemd/otto-bgp.timer /etc/systemd/system/
sudo cp systemd/otto-bgp-autonomous.service /etc/systemd/system/
sudo cp systemd/otto-bgp-autonomous.timer /etc/systemd/system/
sudo cp systemd/otto-bgp-rpki-preflight.service /etc/systemd/system/

# Reload systemd configuration
sudo systemctl daemon-reload
```

### 2. Configure Environment

```bash
# Create configuration directory
sudo mkdir -p /etc/otto-bgp

# Copy and customize environment configuration
# Choose appropriate template:
# - otto.env.user for user installations
# - otto.env.system for system installations  
# - otto.env.autonomous for autonomous mode
sudo cp systemd/otto.env.system /etc/otto-bgp/otto.env
sudo nano /etc/otto-bgp/otto.env

# Set proper permissions
sudo chown root:otto.bgp /etc/otto-bgp/otto.env
sudo chmod 640 /etc/otto-bgp/otto.env
```

### 3. Choose Deployment Mode

#### Option A: System Mode Only (Manual/Interactive)
```bash
# Enable system mode timer
sudo systemctl enable otto-bgp.timer
sudo systemctl start otto-bgp.timer
```

#### Option B: Autonomous Mode Only (Production)
```bash
# Enable autonomous mode with RPKI preflight
sudo systemctl enable otto-bgp-rpki-preflight.service
sudo systemctl enable otto-bgp-autonomous.timer
sudo systemctl start otto-bgp-autonomous.timer
```

#### Option C: Both Modes (Hybrid)
```bash
# Enable both timers (adjust schedules to avoid conflicts)
sudo systemctl enable otto-bgp.timer
sudo systemctl enable otto-bgp-autonomous.timer
sudo systemctl enable otto-bgp-rpki-preflight.service
sudo systemctl start otto-bgp.timer
sudo systemctl start otto-bgp-autonomous.timer
```

### 4. Verify Operation

```bash
# Check timer status
sudo systemctl status otto-bgp.timer
sudo systemctl status otto-bgp-autonomous.timer

# View timer schedules
sudo systemctl list-timers otto-bgp*

# Check service logs
sudo journalctl -u otto-bgp.service -f
sudo journalctl -u otto-bgp-autonomous.service -f
sudo journalctl -u otto-bgp-rpki-preflight.service -f
```

## Service Configuration

### Execution
- **User**: `otto.bgp` (dedicated service user)
- **Working Directory**: `/opt/otto-bgp`
- **Command**: Runs full pipeline with devices from `/etc/otto-bgp/devices.csv`
- **Output**: Policy files written to `/var/lib/otto-bgp/output`

### Security Features
- **Privilege Restrictions**: `NoNewPrivileges=yes`
- **File System Protection**: `ProtectSystem=strict`
- **Resource Limits**: 1GB memory, 50% CPU quota
- **Network Access**: Required for SSH connections and bgpq4 queries
- **Read-Only Paths**: Configuration and application directories
- **Read-Write Paths**: Output and log directories only

### Timing
- **Schedule**: Hourly execution at the top of each hour
- **Persistence**: Catches up missed runs if system was down
- **Randomization**: Up to 5-minute random delay to prevent network congestion
- **Timeout**: 5-minute startup timeout, 1-minute shutdown timeout

## Directory Structure

The service expects the following directory layout:

```
/opt/otto-bgp/                    # Application directory (read-only)
├── otto_bgp/                     # Python package
├── otto-bgp                      # Main executable
└── README.md                     # Documentation

/etc/otto-bgp/                    # Configuration directory (read-only)
├── config.json                   # Main configuration
├── devices.csv                   # Device inventory
└── environment                   # Environment variables

/var/lib/otto-bgp/                # Data directory (read-write)
├── venv/                         # Python virtual environment
├── output/                       # Generated policy files
├── logs/                         # Log files
└── ssh-keys/                     # SSH keys and known_hosts
```

## Troubleshooting

### Check Service Status
```bash
sudo systemctl status otto-bgp.service
sudo systemctl status otto-bgp.timer
```

### View Logs
```bash
# Recent logs
sudo journalctl -u otto-bgp.service -n 50

# Follow logs in real-time
sudo journalctl -u otto-bgp.service -f

# Logs for specific time period
sudo journalctl -u otto-bgp.service --since "1 hour ago"
```

### Manual Execution
```bash
# Run service manually (as otto.bgp user)
sudo -u otto.bgp /var/lib/otto-bgp/venv/bin/python /opt/otto-bgp/otto_bgp/main.py pipeline /etc/otto-bgp/devices.csv --output-dir /var/lib/otto-bgp/output

# Test timer manually
sudo systemctl start otto-bgp.service
```

### Common Issues

1. **Permission Denied**: Check file ownership and permissions
   ```bash
   sudo chown -R otto.bgp:otto.bgp /var/lib/otto-bgp
   sudo chmod 600 /var/lib/otto-bgp/ssh-keys/otto-bgp
   ```

2. **SSH Key Issues**: Verify host keys are collected
   ```bash
   sudo -u otto.bgp ssh-keygen -l -f /var/lib/otto-bgp/ssh-keys/known_hosts
   ```

3. **Python Environment**: Check virtual environment
   ```bash
   sudo -u otto.bgp /var/lib/otto-bgp/venv/bin/python --version
   sudo -u otto.bgp /var/lib/otto-bgp/venv/bin/python -c "import paramiko; print('OK')"
   ```

## Security Notes

- Service runs with minimal privileges under dedicated user `otto.bgp`
- File system access is restricted to required directories only
- No shell access or privilege escalation capabilities
- Network access limited to SSH and bgpq4 protocol requirements
- All configuration and secrets stored in protected directories
- Comprehensive logging for security monitoring and troubleshooting