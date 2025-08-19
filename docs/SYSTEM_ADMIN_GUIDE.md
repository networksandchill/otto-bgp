# System Administrator Guide - Otto BGP v0.3.2

## Overview

This guide provides system administrators with the technical details needed to install, configure, and maintain the Otto BGP backend infrastructure. It covers Linux system configuration, service management, monitoring, and troubleshooting procedures.

For Juniper router configuration and network engineering topics, see the Network Engineering Reference guide.

## Service Account Setup

Create otto.bgp system user for service operations:

```bash
# Create system user
useradd -r -s /bin/bash -d /var/lib/otto-bgp otto.bgp

# Create required directories
mkdir -p /var/lib/otto-bgp/{ssh-keys,policies,logs}
mkdir -p /etc/otto-bgp

# Set ownership and permissions
chown -R otto.bgp:otto.bgp /var/lib/otto-bgp
chmod 700 /var/lib/otto-bgp/ssh-keys
chmod 600 /var/lib/otto-bgp/ssh-keys/*

# Configure sudo for specific operations (if needed)
echo "otto.bgp ALL=(root) NOPASSWD: /bin/systemctl reload otto-bgp" >> /etc/sudoers.d/otto-bgp
```

## Systemd Service Configuration

Otto BGP operates as systemd service with timer:

```ini
# /etc/systemd/system/otto-bgp.service
[Unit]
Description=Otto BGP Policy Generator
After=network.target

[Service]
Type=oneshot
User=otto.bgp
Group=otto.bgp
ExecStart=/opt/otto-bgp/venv/bin/python /opt/otto-bgp/otto_bgp/main.py pipeline /etc/otto-bgp/devices.csv --output-dir /var/lib/otto-bgp/output
WorkingDirectory=/opt/otto-bgp
Environment=PYTHONPATH=/opt/otto-bgp
Environment=OTTO_BGP_MODE=system
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
ReadWritePaths=/var/lib/otto-bgp/output
ReadWritePaths=/var/lib/otto-bgp/logs
ReadWritePaths=/var/lib/otto-bgp/cache
ReadOnlyPaths=/etc/otto-bgp
ReadOnlyPaths=/opt/otto-bgp
ReadOnlyPaths=/var/lib/otto-bgp/ssh-keys

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/otto-bgp.timer
[Unit]
Description=Otto BGP Policy Generator Timer
Requires=otto-bgp.service

[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
```

## SSH Host Key Management Operations

### Adding New Router Hosts

When network engineers add new routers to the network, system administrators must update the Otto BGP backend:

**Step 1: Add Device to Inventory**
```bash
# Add new device to devices.csv
echo "192.168.1.100,new-core-router" | sudo tee -a /var/lib/otto-bgp/config/devices.csv

# Verify addition
sudo cat /var/lib/otto-bgp/config/devices.csv
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
sudo /opt/otto-bgp/scripts/setup-host-keys.sh \
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

# If successful, test with Otto BGP
sudo -u otto-bgp /opt/otto-bgp/otto-bgp collect \
    <(echo "192.168.1.100,new-core-router") --test
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
# Monthly: Verify all host keys are still valid
sudo -u otto-bgp /opt/otto-bgp/scripts/verify-host-keys.sh \
    /var/lib/otto-bgp/config/devices.csv \
    /var/lib/otto-bgp/ssh-keys/known_hosts

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
sudo -u otto-bgp /opt/otto-bgp/otto-bgp collect \
    /var/lib/otto-bgp/config/devices.csv --test
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
done < /var/lib/otto-bgp/config/devices.csv

# Generate host key report
sudo tee /tmp/host-key-report.sh << 'EOF'
#!/bin/bash
echo "Otto BGP SSH Host Key Report - $(date)"
echo "=============================================="
echo ""
echo "Known Hosts File: /var/lib/otto-bgp/ssh-keys/known_hosts"
echo "Devices File: /var/lib/otto-bgp/config/devices.csv"
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
User=otto.bgp
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
DEVICES_CSV="/var/lib/otto-bgp/devices.csv"
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
- `OTTO_BGP_MODE` - Set to "autonomous" for unattended operation
- `OTTO_BGP_CONFIG_DIR` - Configuration directory (default: /etc/otto-bgp)
- `OTTO_BGP_DATA_DIR` - Data directory (default: /var/lib/otto-bgp)
- `OTTO_BGP_RPKI_CACHE_DIR` - RPKI cache directory
- `SSH_USERNAME` / `SSH_PASSWORD` - SSH credentials (use keys in production)

**Configuration Files:**
- `/etc/otto-bgp/otto.conf` - Main configuration
- `/var/lib/otto-bgp/ssh-keys/known_hosts` - SSH host keys
- `/var/lib/otto-bgp/rpki/vrp_cache.csv` - RPKI cache

## Log Management

### Log File Locations

Otto BGP generates logs in standard locations:

- **Application Log**: `/var/lib/otto-bgp/logs/otto-bgp.log`
- **Discovery Log**: `/var/lib/otto-bgp/logs/discovery.log`
- **NETCONF Log**: `/var/lib/otto-bgp/logs/netconf.log`
- **Security Events**: `/var/lib/otto-bgp/logs/security.log`
- **Systemd Journal**: `journalctl -u otto-bgp.service`

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
ssh -i /var/lib/otto-bgp/ssh-keys/otto-bgp otto-bgp@router.example.com "show version"

# Verify host key
ssh-keygen -l -f /var/lib/otto-bgp/ssh-keys/known_hosts | grep router.example.com

# Test with verbose SSH debugging
ssh -vvv -i /var/lib/otto-bgp/ssh-keys/otto-bgp otto-bgp@router.example.com
```

### NETCONF Connectivity Testing

```bash
# Test NETCONF subsystem
ssh -p 830 otto-bgp@router.example.com -s netconf

# Verify NETCONF service on router
ssh otto-bgp@router.example.com "show configuration system services netconf"

# Check PyEZ installation
python3 -c "from jnpr.junos import Device; print('PyEZ available')"
```

### Permission Verification

```bash
# Verify user permissions on router
ssh otto-bgp@router.example.com "show cli authorization"

# Test configuration access
ssh otto-bgp@router.example.com "show configuration policy-options | display set"

# Verify commit capability
ssh otto-bgp@router.example.com "configure private; commit check; exit"
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
sudo -u otto.bgp /opt/otto-bgp/otto-bgp --help

# Verify environment variables
sudo -u otto.bgp env | grep OTTO_BGP
```

### File System Permissions

```bash
# Verify directory ownership
ls -la /var/lib/otto-bgp/

# Check SSH key permissions
ls -la /var/lib/otto-bgp/ssh-keys/

# Verify configuration file access
sudo -u otto.bgp cat /etc/otto-bgp/otto.conf

# Test log file access
sudo -u otto.bgp touch /var/lib/otto-bgp/logs/test.log
```

### Security Event Analysis

Monitor logs for security indicators:

```bash
# Authentication failures
grep "Authentication failed" /var/lib/otto-bgp/logs/security.log

# Host key issues
grep "HOST KEY MISMATCH" /var/lib/otto-bgp/logs/security.log

# Permission violations
grep "Permission denied" /var/lib/otto-bgp/logs/otto-bgp.log

# Configuration change tracking
grep "commit" /var/lib/otto-bgp/logs/netconf.log
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

This guide provides system administrators with comprehensive procedures for maintaining Otto BGP backend operations while network engineers focus on router configuration aspects.