# System Administrator Guide - Otto BGP v0.3.2

## Overview

This guide provides system administrators with the technical details needed to install, configure, and maintain the Otto BGP backend infrastructure. It covers Linux system configuration, service management, monitoring, and troubleshooting procedures.

For Juniper router configuration and network engineering topics, see the Network Engineering Reference guide.

## Service Account Setup

Create the Otto BGP system user for service operations (aligns with install.sh defaults):

```bash
useradd -r -s /bin/false -d /var/lib/otto-bgp otto-bgp

# Create required directories
mkdir -p /var/lib/otto-bgp/{ssh-keys,policies,logs}
mkdir -p /etc/otto-bgp

# Set ownership and permissions
chown -R otto-bgp:otto-bgp /var/lib/otto-bgp
chmod 700 /var/lib/otto-bgp/ssh-keys
chmod 600 /var/lib/otto-bgp/ssh-keys/*

# Configure sudo for specific operations (if needed)
echo "otto-bgp ALL=(root) NOPASSWD: /bin/systemctl reload otto-bgp" >> /etc/sudoers.d/otto-bgp
```

## Systemd Service Configuration

Otto BGP provides a standard policy generation service (system mode) and optional autonomous units. The installer (install.sh) creates only the main service and, when not in autonomous mode, a daily timer. The autonomous and RPKI preflight units below are optional manual deployments.

```ini
# /etc/systemd/system/otto-bgp.service (System Mode)
[Unit]
Description=Otto BGP v0.3.2 - System Mode (Policy Generation)
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
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
RestrictRealtime=yes
LockPersonality=yes
RemoveIPC=yes

# File system access
ReadWritePaths=/var/lib/otto-bgp/policies
ReadWritePaths=/var/lib/otto-bgp/logs
ReadOnlyPaths=/etc/otto-bgp
ReadOnlyPaths=/usr/local/lib/otto-bgp
ReadOnlyPaths=/var/lib/otto-bgp/ssh-keys

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/otto-bgp.timer (System Mode schedule)
[Unit]
Description=Otto BGP v0.3.2 System Mode Timer
Requires=otto-bgp.service

[Timer]
OnCalendar=daily
Persistent=true
AccuracySec=1min
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
```

### Autonomous Service and Preflight

Autonomous mode runs end-to-end policy generation and application with safety guardrails. It is gated by an RPKI preflight service that validates VRP cache freshness before each run.

```ini
# /etc/systemd/system/otto-bgp-rpki-preflight.service (Optional)
[Unit]
Description=Otto BGP RPKI Preflight - VRP Freshness Check
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=otto-bgp
Group=otto-bgp
WorkingDirectory=/usr/local/lib/otto-bgp
ExecStart=/usr/local/bin/otto-bgp rpki-check --max-age 86400
Environment=PYTHONPATH=/usr/local/lib/otto-bgp
EnvironmentFile=-/etc/otto-bgp/otto.env

# Hardened permissions (read-only code/config; no home/root access)
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
PrivateUsers=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/otto-bgp-autonomous.service (Optional Autonomous Mode)
[Unit]
Description=Otto BGP - Autonomous Mode (Scheduled Operations)
After=network-online.target otto-bgp-rpki-preflight.service
Wants=network-online.target
Requires=otto-bgp-rpki-preflight.service

[Service]
Type=oneshot
User=otto-bgp
Group=otto-bgp
WorkingDirectory=/usr/local/lib/otto-bgp
ExecStart=/usr/local/bin/otto-bgp pipeline /etc/otto-bgp/devices.csv --output-dir /var/lib/otto-bgp/policies --autonomous
Environment=PYTHONPATH=/usr/local/lib/otto-bgp
Environment=OTTO_BGP_AUTONOMOUS=true
EnvironmentFile=-/etc/otto-bgp/otto.env

# Network segmentation (allow local + RFC1918 by default)
IPAddressDeny=any
IPAddressAllow=localhost
IPAddressAllow=10.0.0.0/8
IPAddressAllow=172.16.0.0/12
IPAddressAllow=192.168.0.0/16

# Filesystem restrictions as above
ReadWritePaths=/var/lib/otto-bgp/policies
ReadWritePaths=/var/lib/otto-bgp/logs
ReadWritePaths=/var/lib/otto-bgp/cache
ReadOnlyPaths=/etc/otto-bgp
ReadOnlyPaths=/usr/local/lib/otto-bgp
ReadOnlyPaths=/var/lib/otto-bgp/ssh-keys

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/otto-bgp-autonomous.timer (Autonomous schedule)
[Unit]
Description=Otto BGP Autonomous Mode Scheduler
Requires=otto-bgp-autonomous.service

[Timer]
OnCalendar=*-*-* 08,12,16,20:00:00
Persistent=yes
AccuracySec=1min
RandomizedDelaySec=900

[Install]
WantedBy=timers.target
```

Enable and start the timers:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now otto-bgp.timer
# Optional autonomous scheduling (only if optional autonomous units are installed)
# sudo systemctl enable --now otto-bgp-autonomous.timer
```

Monitoring logs:

```bash
sudo journalctl -u otto-bgp.service -f
# Optional units (if installed):
# sudo journalctl -u otto-bgp-autonomous.service -f | grep -Ei "autonomous|netconf|commit|rpki"
# sudo systemctl status otto-bgp-rpki-preflight.service
```

## SSH Host Key Management Operations

### Adding New Router Hosts

When network engineers add new routers to the network, system administrators must update the Otto BGP backend:

**Step 1: Add Device to Inventory**
```bash
# Add new device to devices.csv (system unit uses /etc/otto-bgp/devices.csv)
echo "address,hostname" | sudo tee /etc/otto-bgp/devices.csv
echo "192.168.1.100,new-core-router" | sudo tee -a /etc/otto-bgp/devices.csv

# Verify addition
sudo cat /etc/otto-bgp/devices.csv
```

**Step 2: Provide SSH Public Key to Network Team**
```bash
# Display the Otto BGP public key for router configuration
sudo cat /var/lib/otto-bgp/ssh-keys/otto-bgp.pub

# Network engineers will configure this key on the router:
# set system login user bgp-read authentication ssh-ed25519 "ssh-ed25519 AAAAC3Nz... otto-bgp@hostname"
```

**Step 3: Collect Host Key from New Device**
```bash
# Method 1: Use setup script for single device
sudo /usr/local/lib/otto-bgp/scripts/setup-host-keys.sh \
    <(echo "192.168.1.100,new-core-router") \
    /tmp/new-host-key.tmp

# Verify collected key
sudo -u otto-bgp ssh-keygen -l -f /tmp/new-host-key.tmp

# Method 2: Manual collection (if script unavailable)
sudo -u otto-bgp ssh-keyscan -t ed25519,rsa 192.168.1.100 > /tmp/new-host-key.tmp
```

**Step 4: Security Verification**
```bash
# CRITICAL: Verify fingerprint matches network team's documentation
sudo -u otto-bgp ssh-keygen -l -f /tmp/new-host-key.tmp

# Compare this output with network team's device records
# Each device should have a unique, documented fingerprint
# DO NOT proceed if fingerprint doesn't match official records
```

**Step 5: Add to Known Hosts**
```bash
# Backup current known_hosts
sudo cp /var/lib/otto-bgp/ssh-keys/known_hosts \
    /var/lib/otto-bgp/ssh-keys/known_hosts.backup.$(date +%Y%m%d)

# Add new host key
sudo cat /tmp/new-host-key.tmp >> /var/lib/otto-bgp/ssh-keys/known_hosts

# Clean up temporary file
sudo rm /tmp/new-host-key.tmp

# Set proper ownership
sudo chown otto-bgp:otto-bgp /var/lib/otto-bgp/ssh-keys/known_hosts
```

**Step 6: Test Connectivity**
```bash
# Test SSH connection with strict host checking
sudo -u otto-bgp ssh -i /var/lib/otto-bgp/ssh-keys/otto-bgp \
    -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile=/var/lib/otto-bgp/ssh-keys/known_hosts \
    bgp-read@192.168.1.100 "show version | match Model"

# If successful, test collection with Otto BGP using the CSV file
otto-bgp collect /etc/otto-bgp/devices.csv --output-dir /var/lib/otto-bgp/policies
```

### Handling Host Key Changes

When routers undergo maintenance that regenerates SSH host keys, system administrators must update the backend files:

**Detection: Connection Failures with Host Key Mismatch**
```bash
# Otto BGP will fail with host key warnings like:
# "WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!"
# "Host key verification failed"

# Service logs will show SSH failures
sudo journalctl -u otto-bgp.service | grep -i "host key"
```

**Emergency Response Procedure**

**Step 1: Coordinate with Network Team**
```bash
# DO NOT proceed without network team verification
# Contact network engineers to confirm:
# 1. Was planned maintenance performed on this device?
# 2. Was the device replaced or upgraded?
# 3. What is the expected new fingerprint from router console?

# Check maintenance logs and change management records
```

**Step 2: Remove Old Host Key**
```bash
# Backup known_hosts before changes
sudo cp /var/lib/otto-bgp/ssh-keys/known_hosts \
    /var/lib/otto-bgp/ssh-keys/known_hosts.backup.$(date +%Y%m%d-%H%M)

# Remove old key for specific host (replace IP with actual)
sudo -u otto-bgp ssh-keygen -R 192.168.1.1 \
    -f /var/lib/otto-bgp/ssh-keys/known_hosts

# Verify removal
sudo -u otto-bgp grep -v "^192.168.1.1" /var/lib/otto-bgp/ssh-keys/known_hosts
```

**Step 3: Collect New Host Key**
```bash
# Collect new host key
sudo -u otto-bgp ssh-keyscan -t ed25519,rsa 192.168.1.1 > /tmp/new-key-192.168.1.1

# Display new fingerprint for verification
sudo -u otto-bgp ssh-keygen -l -f /tmp/new-key-192.168.1.1

# CRITICAL: Compare this fingerprint with network team's official records
# If fingerprints don't match, DO NOT proceed - investigate potential security incident
```

**Step 4: Manual Verification**
```bash
# SSH manually with host key bypass (ONE TIME ONLY for verification)
sudo -u otto-bgp ssh -i /var/lib/otto-bgp/ssh-keys/otto-bgp \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    bgp-read@192.168.1.1 "show version | match Model; show system uptime"

# Verify device details match network team's records:
# - Model number should match inventory
# - Uptime should align with maintenance window
# - Device should respond with expected configuration
```

**Step 5: Add New Host Key**
```bash
# Only proceed if Step 4 verification is successful
sudo cat /tmp/new-key-192.168.1.1 >> /var/lib/otto-bgp/ssh-keys/known_hosts

# Set proper ownership
sudo chown otto-bgp:otto-bgp /var/lib/otto-bgp/ssh-keys/known_hosts

# Clean up
sudo rm /tmp/new-key-192.168.1.1
```

**Step 6: Test and Verify**
```bash
# Test strict host checking with new key
sudo -u otto-bgp ssh -i /var/lib/otto-bgp/ssh-keys/otto-bgp \
    -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile=/var/lib/otto-bgp/ssh-keys/known_hosts \
    bgp-read@192.168.1.1 "show bgp neighbor | count"

# Test with Otto BGP
sudo systemctl start otto-bgp.service
sudo systemctl status otto-bgp.service
```

**Security Alert: If Verification Fails**
```bash
# If device doesn't respond correctly or fingerprints don't match:
# 1. DO NOT add the new key
# 2. Alert network team for device isolation if needed
# 3. Contact security team immediately
# 4. Preserve logs for investigation

# Restore backup if needed
sudo cp /var/lib/otto-bgp/ssh-keys/known_hosts.backup.* \
    /var/lib/otto-bgp/ssh-keys/known_hosts
```

### Host Key Collection and Management

**Initial Host Key Collection**
```bash
# Manual host key collection for initial setup
ssh-keyscan -t ed25519,rsa -H 192.168.1.1 >> /var/lib/otto-bgp/ssh-keys/known_hosts
ssh-keyscan -t ed25519,rsa -H router.example.com >> /var/lib/otto-bgp/ssh-keys/known_hosts

# Verify collected keys
ssh-keygen -l -f /var/lib/otto-bgp/ssh-keys/known_hosts
```

**Known Hosts File Format**

Known_hosts entries use SSH standard format with hashed hostnames:

```
|1|base64hash|base64hash ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExample
|1|base64hash|base64hash ssh-rsa AAAAB3NzaC1yc2EAAAAExample
```

**Host Key Rotation Management**

When network engineers perform router maintenance that regenerates keys:

1. Network team notifies system administrators of planned key rotation
2. System administrators remove old entries from known_hosts file
3. Collect new host keys using ssh-keyscan after router work completes
4. Verify fingerprints match network team's documentation before production use

### Security Verification & Backup Procedures

**Regular Maintenance Schedule**
```bash
# Monthly: Re-validate host keys against devices
sudo /usr/local/lib/otto-bgp/scripts/setup_host_keys.py \
    --devices /etc/otto-bgp/devices.csv \
    --output /tmp/known_hosts.revalidated

# Compare fingerprints before replacing known_hosts
ssh-keygen -l -f /var/lib/otto-bgp/ssh-keys/known_hosts > /tmp/known_hosts.current.fps
ssh-keygen -l -f /tmp/known_hosts.revalidated > /tmp/known_hosts.new.fps
diff -u /tmp/known_hosts.current.fps /tmp/known_hosts.new.fps || true

# Weekly: Create known_hosts backup
sudo cp /var/lib/otto-bgp/ssh-keys/known_hosts \
    /var/lib/otto-bgp/ssh-keys/backups/known_hosts.$(date +%Y%m%d)

# Quarterly: Audit SSH access logs
sudo journalctl -u otto-bgp.service --since "3 months ago" | \
    grep -E "(ssh|host key|authentication)" > /tmp/ssh-audit.log
```

**Backup Procedures**
```bash
# Create backup directory structure
sudo mkdir -p /var/lib/otto-bgp/ssh-keys/backups
sudo chown otto-bgp:otto-bgp /var/lib/otto-bgp/ssh-keys/backups

# Automated daily backup (add to cron)
sudo tee /etc/cron.daily/otto-bgp-ssh-backup << 'EOF'
#!/bin/bash
# Backup SSH keys and known_hosts daily
BACKUP_DIR="/var/lib/otto-bgp/ssh-keys/backups"
DATE=$(date +%Y%m%d)

# Backup known_hosts
cp /var/lib/otto-bgp/ssh-keys/known_hosts "$BACKUP_DIR/known_hosts.$DATE"

# Backup SSH keys (encrypted)
tar -czf "$BACKUP_DIR/ssh-keys.$DATE.tar.gz" \
    /var/lib/otto-bgp/ssh-keys/otto-bgp* \
    /var/lib/otto-bgp/ssh-keys/known_hosts

# Cleanup old backups (keep 30 days)
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +30 -delete
find "$BACKUP_DIR" -name "known_hosts.*" -mtime +30 -delete

chown -R otto-bgp:otto-bgp "$BACKUP_DIR"
EOF

sudo chmod +x /etc/cron.daily/otto-bgp-ssh-backup
```

**Recovery Procedures**
```bash
# List available backups
ls -la /var/lib/otto-bgp/ssh-keys/backups/

# Restore known_hosts from backup (replace date)
sudo cp /var/lib/otto-bgp/ssh-keys/backups/known_hosts.20241215 \
    /var/lib/otto-bgp/ssh-keys/known_hosts

# Restore full SSH key backup
sudo tar -xzf /var/lib/otto-bgp/ssh-keys/backups/ssh-keys.20241215.tar.gz \
    -C / --overwrite

# Set proper permissions after recovery
sudo chown otto-bgp:otto-bgp /var/lib/otto-bgp/ssh-keys/*
sudo chmod 600 /var/lib/otto-bgp/ssh-keys/otto-bgp
sudo chmod 644 /var/lib/otto-bgp/ssh-keys/otto-bgp.pub
sudo chmod 644 /var/lib/otto-bgp/ssh-keys/known_hosts

# Test recovery
otto-bgp collect /etc/otto-bgp/devices.csv --output-dir /var/lib/otto-bgp/policies
```

**Security Audit & Verification**
```bash
# Verify known_hosts integrity
sudo -u otto-bgp ssh-keygen -H -F nonexistent 2>/dev/null || echo "known_hosts format OK"

# Check for duplicate entries
sudo sort /var/lib/otto-bgp/ssh-keys/known_hosts | uniq -d

# Verify all devices in CSV have host keys
while IFS=',' read -r ip hostname; do
    if [ "$ip" != "address" ]; then  # Skip header
        if ! grep -q "^$ip " /var/lib/otto-bgp/ssh-keys/known_hosts; then
            echo "WARNING: No host key for $ip ($hostname)"
        fi
    fi
done < /etc/otto-bgp/devices.csv

# Generate host key report
sudo tee /tmp/host-key-report.sh << 'EOF'
#!/bin/bash
echo "Otto BGP SSH Host Key Report - $(date)"
echo "=============================================="
echo ""
echo "Known Hosts File: /var/lib/otto-bgp/ssh-keys/known_hosts"
echo "Devices File: /etc/otto-bgp/devices.csv"
echo ""
echo "Host Key Summary:"
wc -l /var/lib/otto-bgp/ssh-keys/known_hosts
echo ""
echo "Host Key Details:"
sudo -u otto-bgp ssh-keygen -l -f /var/lib/otto-bgp/ssh-keys/known_hosts
EOF

sudo chmod +x /tmp/host-key-report.sh
sudo /tmp/host-key-report.sh
```

### SSH Host Key Monitoring & Alerting

**Monitoring & Alerting**
```bash
# Create systemd service for host key monitoring
sudo tee /etc/systemd/system/otto-bgp-ssh-monitor.service << 'EOF'
[Unit]
Description=Otto BGP SSH Host Key Monitor
After=network.target

[Service]
Type=oneshot
User=otto-bgp
ExecStart=/usr/local/bin/otto-bgp-ssh-monitor
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Create monitoring script
sudo tee /usr/local/bin/otto-bgp-ssh-monitor << 'EOF'
#!/bin/bash
# Monitor SSH host key health

KNOWN_HOSTS="/var/lib/otto-bgp/ssh-keys/known_hosts"
DEVICES_CSV="/etc/otto-bgp/devices.csv"
LOG_PREFIX="OTTO-BGP-SSH-MONITOR"

# Check if known_hosts file exists and is readable
if [ ! -r "$KNOWN_HOSTS" ]; then
    logger -t "$LOG_PREFIX" "ERROR: Cannot read known_hosts file: $KNOWN_HOSTS"
    exit 1
fi

# Check if devices.csv exists
if [ ! -r "$DEVICES_CSV" ]; then
    logger -t "$LOG_PREFIX" "ERROR: Cannot read devices.csv: $DEVICES_CSV"
    exit 1
fi

# Count devices vs host keys
DEVICE_COUNT=$(grep -v "^address," "$DEVICES_CSV" | wc -l)
HOST_KEY_COUNT=$(wc -l < "$KNOWN_HOSTS")

logger -t "$LOG_PREFIX" "INFO: Monitoring $DEVICE_COUNT devices with $HOST_KEY_COUNT host keys"

# Check for missing host keys
MISSING=0
while IFS=',' read -r ip hostname; do
    if [ "$ip" != "address" ] && [ -n "$ip" ]; then
        if ! grep -q "^$ip " "$KNOWN_HOSTS"; then
            logger -t "$LOG_PREFIX" "WARNING: Missing host key for $ip ($hostname)"
            MISSING=$((MISSING + 1))
        fi
    fi
done < "$DEVICES_CSV"

if [ $MISSING -gt 0 ]; then
    logger -t "$LOG_PREFIX" "ERROR: $MISSING devices missing host keys"
    exit 1
else
    logger -t "$LOG_PREFIX" "INFO: All devices have host keys configured"
fi
EOF

sudo chmod +x /usr/local/bin/otto-bgp-ssh-monitor

# Create timer for regular monitoring
sudo tee /etc/systemd/system/otto-bgp-ssh-monitor.timer << 'EOF'
[Unit]
Description=Run Otto BGP SSH Monitor Daily
Requires=otto-bgp-ssh-monitor.service

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
EOF

# Enable monitoring
sudo systemctl daemon-reload
sudo systemctl enable otto-bgp-ssh-monitor.timer
sudo systemctl start otto-bgp-ssh-monitor.timer
```

## Environment Configuration

### System vs Autonomous Mode

Configuration differences between operational modes:

| Parameter | System Mode | Autonomous Mode |
|-----------|-------------|-----------------|
| SSH Host Verification | Strict | Strict |
| NETCONF Application | Enabled | Enabled |
| Commit Process | Manual confirmation required | Automatic based on risk assessment |
| Confirmation Timeout | Set by operator | 120 seconds default |
| Change Validation | Manual review | Automated with safety checks |
| Rollback Policy | Manual operator decision | Automatic on timeout or failure |

Both modes use NETCONF for policy application. System mode requires operator confirmation before committing changes. Autonomous mode commits automatically for changes that pass safety validation.

### Environment Variables

**Configuration Variables:**
- `OTTO_BGP_MODE`: set to `autonomous` for unattended operation (used in some sample units; the CLI primarily keys on `OTTO_BGP_AUTONOMOUS`).
- `OTTO_BGP_AUTONOMOUS`: `true` to run pipeline in autonomous mode.
- `OTTO_BGP_CONFIG_DIR`: configuration directory (default: `/etc/otto-bgp`).
- `OTTO_BGP_DATA_DIR`: data directory (default: `/var/lib/otto-bgp`).
- `OTTO_BGP_LOG_FILE`: optional file path to enable file logging in addition to journal.
- `OTTO_BGP_LOG_LEVEL`: log level (`INFO`, `DEBUG`, etc.).
- `OTTO_BGP_RPKI_VRP_CACHE`: path to VRP cache file (default: `/var/lib/otto-bgp/rpki/vrp_cache.json`).
- `OTTO_BGP_RPKI_ALLOWLIST`: path to NOTFOUND allowlist file (default: `/var/lib/otto-bgp/rpki/allowlist.json`).
- `SSH_USERNAME` / `SSH_PASSWORD`: SSH credentials (key-based auth recommended).

**Configuration Files:**
- `/etc/otto-bgp/config.json`: main configuration (optional; environment variables also supported).
- `/etc/otto-bgp/otto.env`: environment variables loaded by services/wrapper.
- `/var/lib/otto-bgp/ssh-keys/known_hosts`: SSH host keys.
- `/var/lib/otto-bgp/rpki/vrp_cache.json`: RPKI cache (JSON).

## IRR Proxy Configuration

### Overview

Use the IRR proxy when direct whois/IRR access is blocked by firewalls or network restrictions. Otto establishes SSH local-port tunnels to IRR servers and redirects bgpq4 queries through `127.0.0.1:<local_port>`.

**Key Features:**
- Multiple tunnel support for redundancy and load distribution
- Automatic tunnel health monitoring and reconnection
- Strict SSH host key verification for security
- Parallel tunnel establishment for improved performance

### Configuration Requirements

**IRR proxy requires JSON configuration** due to its complex nested structure with multiple tunnels, each having distinct parameters. While basic settings can be set via environment variables, tunnel definitions must be specified in `/etc/otto-bgp/config.json`.

**Why JSON is Required:**
- **Complex array structures**: Multiple tunnels with individual parameters
- **Clear validation**: Structured validation of tunnel configurations  
- **Maintainability**: Easier to read and modify than 15+ environment variables
- **Error prevention**: Reduces misconfiguration risks from manual env var setup

### Complete Configuration Example

`/etc/otto-bgp/config.json`:
```json
{
  "irr_proxy": {
    "enabled": true,
    "jump_host": "bastion.example.com", 
    "jump_user": "admin",
    "ssh_key_file": "/var/lib/otto-bgp/ssh-keys/proxy-key",
    "known_hosts_file": "/var/lib/otto-bgp/ssh-keys/proxy-known-hosts",
    "connection_timeout": 30,
    "health_check_interval": 300,
    "max_retries": 3,
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
      },
      {
        "name": "whois-arin",
        "local_port": 43003,
        "remote_host": "whois.arin.net",
        "remote_port": 43
      }
    ]
  }
}
```

### Environment Variable Overrides

Basic settings can be overridden via environment variables:

- `OTTO_BGP_PROXY_ENABLED`: `true|1|yes` to enable
- `OTTO_BGP_PROXY_JUMP_HOST`: proxy jump host
- `OTTO_BGP_PROXY_JUMP_USER`: proxy jump user  
- `OTTO_BGP_PROXY_SSH_KEY`: path to private key
- `OTTO_BGP_PROXY_KNOWN_HOSTS`: path to known_hosts for the jump host

**Note**: Tunnel configurations cannot be set via environment variables and must be defined in JSON.

Key and host key setup for the proxy jump host:

```bash
# Create dedicated files for the proxy (separate from router keys)
sudo install -d -m 700 -o otto-bgp -g otto-bgp /var/lib/otto-bgp/ssh-keys
sudo -u otto-bgp ssh-keyscan -t ed25519,rsa bastion.example.com > /var/lib/otto-bgp/ssh-keys/proxy-known-hosts
sudo chown otto-bgp:otto-bgp /var/lib/otto-bgp/ssh-keys/proxy-known-hosts
sudo chmod 644 /var/lib/otto-bgp/ssh-keys/proxy-known-hosts

# Place the proxy private key and set permissions
sudo chown otto-bgp:otto-bgp /var/lib/otto-bgp/ssh-keys/proxy-key
sudo chmod 600 /var/lib/otto-bgp/ssh-keys/proxy-key
```

Validation and diagnostics:

```bash
# Validate config and establish tunnels to each IRR server
otto-bgp test-proxy --timeout 15

# Optionally run a bgpq4 test through the proxy
otto-bgp test-proxy --test-bgpq4 --timeout 20
```

Operational notes:

- Proxy lifecycle: When `irr_proxy.enabled` is true, `otto-bgp policy` and the unified `pipeline` automatically establish tunnels and clean them up when finished. Use `otto-bgp test-proxy` to validate configuration and connectivity.
- Multiple tunnels: Used for redundancy. When generating policies, the first CONNECTED tunnel is selected automatically; no load balancing between tunnels.
- Containerized bgpq4: Proxy use requires native bgpq4. Docker/Podman modes do not include host networking, so `-h 127.0.0.1 -p <port>` from inside a container will not reach host SSH tunnels.
- Parallelism: With proxy enabled, worker processes are automatically capped (max 4) and receive a snapshot of tunnel endpoints.

## Log Management

### Log Outputs

- Default: logs emit to the systemd journal (`journalctl -u otto-bgp.service`).
- Optional file: set `OTTO_BGP_LOG_FILE` (and optionally `OTTO_BGP_LOG_LEVEL`) in `/etc/otto-bgp/otto.env` to enable a rotating file log. Example:

```bash
echo 'OTTO_BGP_LOG_FILE=/var/lib/otto-bgp/logs/otto-bgp.log' | sudo tee -a /etc/otto-bgp/otto.env
echo 'OTTO_BGP_LOG_LEVEL=INFO' | sudo tee -a /etc/otto-bgp/otto.env
```

### Syslog Integration

Configure rsyslog for centralized logging:

```bash
# /etc/rsyslog.d/otto-bgp.conf
$ModLoad imfile

# Otto BGP application logs
$InputFileName /var/lib/otto-bgp/logs/otto-bgp.log
$InputFileTag otto-bgp:
$InputFileStateFile otto-bgp-state
$InputFileSeverity info
$InputRunFileMonitor

# Send to central syslog server
*.* @@syslog.example.com:514
```

## Troubleshooting Procedures

### SSH Connection Issues

```bash
# Test SSH connectivity
ssh -i /var/lib/otto-bgp/ssh-keys/otto-bgp bgp-read@router.example.com "show version"

# Verify host key
ssh-keygen -l -f /var/lib/otto-bgp/ssh-keys/known_hosts | grep router.example.com

# Test with verbose SSH debugging
ssh -vvv -i /var/lib/otto-bgp/ssh-keys/otto-bgp otto-bgp@router.example.com
```

### NETCONF Connectivity Testing

```bash
# Test NETCONF subsystem
ssh -p 830 bgp-read@router.example.com -s netconf

# Verify NETCONF service on router
ssh bgp-read@router.example.com "show configuration system services netconf"

# Check PyEZ installation
python3 -c "from jnpr.junos import Device; print('PyEZ available')"
```

### Permission Verification

```bash
# Verify user permissions on router
ssh bgp-read@router.example.com "show cli authorization"

# Test configuration access
ssh bgp-read@router.example.com "show configuration policy-options | display set"

# Verify commit capability
ssh bgp-read@router.example.com "configure private; commit check; exit"
```

### Service Status and Diagnostics

```bash
# Check service status
sudo systemctl status otto-bgp.service
sudo systemctl status otto-bgp.timer

# View service logs
sudo journalctl -u otto-bgp.service -f

# Check service configuration
sudo systemctl show otto-bgp.service

# Test manual execution
otto-bgp --help

# Verify environment variables
sudo -u otto-bgp env | grep -E '^(SSH_|OTTO_BGP_)'
```

### File System Permissions

```bash
# Verify directory ownership
ls -la /var/lib/otto-bgp/

# Check SSH key permissions
ls -la /var/lib/otto-bgp/ssh-keys/

# Verify configuration file access
sudo -u otto-bgp cat /etc/otto-bgp/otto.env

# Test log file access
sudo -u otto-bgp touch /var/lib/otto-bgp/logs/test.log
```

### Security Event Analysis

Monitor logs for security indicators:

```bash
# Authentication failures
sudo journalctl -u otto-bgp.service | grep -i "auth"

# Host key issues
sudo journalctl -u otto-bgp.service | grep -Ei "host key|REMOTE HOST IDENTIFICATION"

# Permission violations
sudo journalctl -u otto-bgp.service | grep -i "permission denied"

# Configuration change tracking
sudo journalctl -u otto-bgp.service | grep -i "commit"
```

## Maintenance Procedures

### Regular System Maintenance

**Daily Tasks:**
- Check service status and logs
- Verify backup creation
- Monitor disk space usage

**Weekly Tasks:**
- Review security event logs
- Test SSH connectivity to sample routers
- Validate configuration file integrity

**Monthly Tasks:**
- Update SSH host key verification
- Review and rotate log files
- Performance monitoring and optimization

### System Updates

When updating Otto BGP:

1. Stop services: `sudo systemctl stop otto-bgp.timer otto-bgp.service`
2. Backup configuration and data directories
3. Update application code
4. Test configuration compatibility
5. Restart services: `sudo systemctl start otto-bgp.timer`
   (If using optional autonomous units, also start `otto-bgp-autonomous.timer`.)
6. Verify operation with test run

### Disaster Recovery

**Backup Strategy:**
- Configuration files: `/etc/otto-bgp/`
- SSH keys: `/var/lib/otto-bgp/ssh-keys/`
- Application data: `/var/lib/otto-bgp/`
- Service definitions: `/etc/systemd/system/otto-bgp.*`

**Recovery Procedure:**
1. Restore system user and directories
2. Restore configuration files
3. Restore SSH keys with proper permissions
4. Restore systemd service files
5. Test connectivity and functionality
6. Resume automated operations

This guide provides system administrators with procedures for maintaining Otto BGP backend operations while network engineers focus on router configuration aspects.
## Known Gaps and Limitations

- Installer scope: `install.sh` creates only `otto-bgp.service` and (when not in autonomous mode) a daily `otto-bgp.timer`. The autonomous and RPKI preflight units shown here are optional manual deployments and are not created by the installer.
- Path conventions: System installations use `/usr/local/bin` (wrapper), `/usr/local/lib/otto-bgp` (code), and `/usr/local/venv` (venv). The sample units under `systemd/` use `/opt/otto-bgp` and are intended for manual deployments.
- Devices inventory: The service expects `/etc/otto-bgp/devices.csv` to exist. The installer does not create this file; administrators must provide it.
- Email recipients: Notification recipients (`to_addresses`) are not read from environment variables. Configure them in `/etc/otto-bgp/config.json` under `autonomous_mode.notifications.email.to_addresses`.
- No config CLI: There is no `otto-bgp config` command. Edit `/etc/otto-bgp/otto.env` and/or `/etc/otto-bgp/config.json`.
- Logging: By default logs go to the journal. A single rotating file log is supported via `OTTO_BGP_LOG_FILE`. Separate `security.log`/`netconf.log` files are not created by the application.
- IRR proxy lifecycle: With `irr_proxy.enabled`, both `policy` and `pipeline` automatically create tunnels and clean them up on exit. There is no load balancing between tunnels; the first CONNECTED tunnel is used.
- Proxy + parallel generation: When proxy is active, workers are capped to 4 and receive a snapshot of tunnel endpoints. You can limit workers with `OTTO_BGP_BGPQ4_MAX_WORKERS` as needed.
- Tunnel selection detail: An `irr_server` hint exists in the generator API but is not exposed via CLI.
