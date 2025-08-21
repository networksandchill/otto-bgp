# Otto BGP Automation Guide

## Table of Contents
1. [Introduction](#introduction)
2. [Known Gaps and Limitations](#known-gaps-and-limitations)
3. [Quick Start](#quick-start)
4. [Automation Workflows](#automation-workflows)
5. [CLI Commands](#cli-commands)
6. [Configuration](#configuration)
7. [Integration](#integration)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)

## Introduction

Otto BGP v0.3.2 provides a router-aware pipeline to collect BGP context via SSH, extract ASNs, and generate bgpq4 policies. It also includes a NETCONF applier with safety controls and an optional autonomous mode with risk-based decisions and email notifications. This guide reflects the current codebase (v0.3.2) behavior and known limitations.

## Known Gaps and Limitations

**Design decisions (working as intended):**
- Autonomous mode enablement: Two-key design (config + CLI flag) for safety. Requires both `autonomous_mode.enabled = true` and `--autonomous` at runtime.

**Current limitations:**
- File logging: Console logging is default; file logging requires explicit configuration (`logging.log_to_file: true`, `logging.log_file`). Use `journalctl -u ...` for systemd logs.
- PyEZ dependency: Policy application and autonomous NETCONF operations require PyEZ libraries (`junos-eznc`, `jxmlease`, `lxml`, `ncclient`). Without these, `apply` and autonomous application will fail.
- Device CSV fields: Router‑aware paths expect an `address` column (with optional `hostname`). The legacy loader accepts `address`/`ip`/`host`. Prefer `address[,hostname]` for consistency.
- Known hosts and SSH hardening: NETCONF/SSH use strict host key checking and default known hosts at `/var/lib/otto-bgp/ssh-keys/known_hosts`. Ensure device host keys are present.
- Email notifications: Best‑effort only. Notifications send on connect/preview/commit/rollback/disconnect when `autonomous_mode.notifications.email.enabled` is true and SMTP settings are valid. No retry/backoff beyond SMTP behavior.

## Operational Modes

Otto BGP operates in three distinct modes to serve different operational needs:

### Systemd Services (Scheduled Execution)
- **Purpose**: Headless, unattended policy generation (system or autonomous mode)
- **Execution**: systemd units and timers are provided in `systemd/`
  - `otto-bgp.timer` runs hourly (top of hour) with randomized delay
  - `otto-bgp-autonomous.timer` runs at 08:00, 12:00, 16:00, 20:00 with randomized delay
- **Operation**: Runs `otto-bgp pipeline ...` with configured devices and output dir
- **Scope**: Policy generation; autonomous application depends on configuration and mode
- **Notes**: File logging is not enabled by default; use `journalctl` for logs

### CLI Tool (Interactive Operations)
- **Purpose**: On-demand execution for testing, debugging, and ad-hoc tasks
- **Execution**: Manual operator-initiated commands
- **Operation**: Flexible command structure (`collect`, `process`, `policy`, `apply`)
- **Scope**: Full policy generation and application capabilities with safety controls
- **Use Case**: Testing connectivity, generating specific policies, troubleshooting, autonomous operation
- **Benefits**: Immediate feedback, custom parameters, development workflows, autonomous mode support

### Autonomous Mode (Full Automation)
- **Purpose**: End-to-end automation including policy application
- **Execution**: `otto-bgp pipeline ... --autonomous` or the `otto-bgp-autonomous.service/timer`
- **Operation**: Pipeline with unified safety manager; email notifications if configured
- **Scope**: Low-risk changes are auto-applied; high-risk require manual intervention
- **Notes**: Must be enabled in config; recommend system installation. RPKI preflight is enforced via `otto-bgp rpki-check` before autonomous runs.

**Example Usage:**
```bash
# Systemd (scheduled)
sudo systemctl enable otto-bgp.timer && sudo systemctl start otto-bgp.timer
sudo systemctl enable otto-bgp-autonomous.timer && sudo systemctl start otto-bgp-autonomous.timer

# CLI (interactive)
./otto-bgp policy input.txt --test --test-as 13335
./otto-bgp collect devices.csv -v

# Autonomous pipeline
./otto-bgp pipeline devices.csv --autonomous --mode autonomous
```

## Quick Start

### Basic Automation Pipeline

```bash
# 1. Run the router-aware pipeline (SSH collect → ASN extract → bgpq4 generate)
./otto-bgp pipeline devices.csv --output-dir policies

# 2. Review generated per-router policies
ls -la policies/routers/<router-hostname>/

# 3. Apply to a specific router (manual/safe mode)
NETCONF_USERNAME=admin NETCONF_PASSWORD=secret \
  ./otto-bgp apply --router <router-hostname> --policy-dir policies --dry-run

# 4. Optional: confirmed commit (auto-rollback if not confirmed)
NETCONF_USERNAME=admin NETCONF_PASSWORD=secret \
  ./otto-bgp apply --router <router-hostname> --policy-dir policies --confirm --confirm-timeout 300

# 5. Autonomous pipeline (requires config enablement)
./otto-bgp pipeline devices.csv --output-dir policies --autonomous --mode autonomous
```

## Automation Workflows

### 1. Discovery Workflow

The `discover` subcommand is now fully functional and performs BGP configuration discovery across your router fleet:

```bash
# Basic discovery
./otto-bgp discover devices.csv

# With change detection
./otto-bgp discover devices.csv --show-diff

# List discovered resources
./otto-bgp list routers --output-dir policies
./otto-bgp list as --output-dir policies
./otto-bgp list groups --output-dir policies
```

The discovery creates YAML mappings under `policies/discovered/` that can be used by the `list` command. Both `discover` and the router-aware `pipeline` are now available for different use cases.

#### Device CSV Format
```csv
hostname,address,username,model,location
edge-router1,10.1.1.1,admin,MX960,datacenter1
core-router1,10.1.2.1,admin,MX480,datacenter1
transit-router1,10.1.3.1,admin,MX240,datacenter2
```

### 2. Policy Generation Workflow

#### Automated Policy Generation

RPKI validation is enabled by default in configuration and used by `policy`/`pipeline` unless `--no-rpki` is provided or RPKI is disabled in config.

```bash
# Generate policies with RPKI validation (default config)
./otto-bgp policy as_list.txt --separate

# Generate with custom output directory (RPKI validation included)
./otto-bgp policy as_list.txt --output-dir policies/routers/router1

# Test BGPq4 connectivity first
./otto-bgp policy as_list.txt --test --test-as 13335

# Disable RPKI validation if needed (not recommended)
./otto-bgp policy as_list.txt --no-rpki --separate
```

**RPKI Validation Features:**
- Default behavior controlled by config; per‑run opt‑out via `--no-rpki`
- Fail‑closed and max age thresholds configurable
- VRP cache and allowlist default to `/var/lib/otto-bgp/rpki/`

#### Router-Specific Generation
The router‑aware `pipeline` writes per‑router outputs under `policies/routers/<hostname>/`. Use that directory with `apply`.

### 3. Policy Application Workflow

#### Safe Application Process
```bash
# 1. Dry run to preview changes
./otto-bgp apply --router lab-router1 --dry-run

# 2. Apply with confirmation (automatic rollback)
./otto-bgp apply --router lab-router1 --confirm --confirm-timeout 120

# 3. Monitor BGP sessions and let auto-rollback handle confirmation timeout
```

#### Batch Application Script
```bash
#!/bin/bash
# apply_to_lab.sh - Apply policies to lab routers

ROUTERS="lab-router1 lab-router2 lab-router3"
POLICY_DIR="policies"

for router in $ROUTERS; do
    echo "Applying policies to $router..."
    
    # Dry run first
    ./otto-bgp apply --router $router --policy-dir $POLICY_DIR --dry-run
    
    # If successful, apply with confirmation
    if [ $? -eq 0 ]; then
        ./otto-bgp apply --router $router --policy-dir $POLICY_DIR \
            --confirm --confirm-timeout 300 --yes
    else
        echo "Dry run failed for $router, skipping..."
    fi
done
```

### 4. Autonomous Operation Workflow

Otto BGP v0.3.2 supports autonomous operation with always‑on guardrails, RPKI validation (config dependent), and email notifications if configured.

#### Setup Autonomous Mode
```bash
# Install with autonomous mode
./install.sh --autonomous

# Configure email notifications during setup:
# - SMTP server and port
# - TLS encryption settings
# - From and to email addresses
# - Subject prefix for notifications
```

#### Autonomous Operation Commands

```bash
# Unified autonomous pipeline
./otto-bgp pipeline devices.csv --autonomous --mode autonomous

# Disable RPKI for this run (not recommended)
./otto-bgp pipeline devices.csv --autonomous --mode autonomous --no-rpki
```

#### Monitoring Autonomous Operations
```bash
# Monitor systemd service for autonomous operations
sudo journalctl -u otto-bgp-autonomous.service -f | grep -i "autonomous\|netconf\|commit"

# Review email notifications for audit trail
```

#### Autonomous Configuration Example
```json
{
  "autonomous_mode": {
    "enabled": true,
    "auto_apply_threshold": 100,
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
        "to_addresses": ["network-team@company.com"],
        "subject_prefix": "[Otto BGP Autonomous]",
        "send_on_success": true,
        "send_on_failure": true
      }
    }
  }
}
```

### 5. IRR Proxy Workflow

For restricted networks where direct IRR access is blocked, enable the proxy in configuration and use the proxy tester to validate SSH tunnel setup. In v0.3.2, `policy` and `pipeline` automatically use the proxy when `irr_proxy.enabled` is true; `test-proxy` provides targeted connectivity checks and an optional bgpq4 test through the proxy.

#### Configure Proxy
```bash
# Set environment variables
export OTTO_BGP_PROXY_ENABLED=true
export OTTO_BGP_PROXY_JUMP_HOST=gateway.example.com
export OTTO_BGP_PROXY_JUMP_USER=admin
export OTTO_BGP_PROXY_SSH_KEY=/path/to/key
export OTTO_BGP_PROXY_KNOWN_HOSTS=/path/to/known_hosts

# Test proxy connectivity and run a bgpq4 test through proxy
./otto-bgp test-proxy --test-bgpq4 -v
```

#### Proxy Configuration File
```json
{
  "irr_proxy": {
    "enabled": true,
    "method": "ssh_tunnel",
    "jump_host": "gateway.example.com",
    "jump_user": "admin",
    "ssh_key_file": "/home/user/.ssh/id_rsa",
    "tunnels": [
      {
        "name": "ntt",
        "local_port": 43001,
        "remote_host": "rr.ntt.net",
        "remote_port": 43
      },
      {
        "name": "radb",
        "local_port": 43002,
        "remote_host": "whois.radb.net",
        "remote_port": 43
      }
    ]
  }
}
```

## CLI Commands

### Core Commands

- `collect`: Collect BGP peer data via SSH (`./otto-bgp collect devices.csv`)
- `process`: Process BGP text or extract ASNs (`./otto-bgp process input.txt --extract-as`)
- `policy`: Generate bgpq4 policies from an AS list (`./otto-bgp policy as_list.txt -s`)
- `apply`: Apply policies via NETCONF with safety controls (`./otto-bgp apply --router R1 --confirm`)
- `pipeline`: Router‑aware end‑to‑end workflow (`./otto-bgp pipeline devices.csv`)
- `list`: List discovered routers/AS/groups (requires prior discovery mappings)
- `test-proxy`: Validate IRR proxy tunnel configuration (`./otto-bgp test-proxy --test-bgpq4`)

### Command Options

#### Global Options
- `--verbose, -v`: Enable verbose logging
- `--quiet, -q`: Warnings only
- `--autonomous` / `--system`: Mode hints; autonomous requires config enablement
- `--dev`: Use Podman for bgpq4 (development)
- `--auto-threshold N`: Informational threshold used in notifications
- `--no-rpki`: Disable RPKI validation for this run

#### Discovery Options
- `devices_csv`: CSV with `address` (and optional `hostname`) columns
- `--output-dir`: Directory for discovered data (default: `policies`)
- `--show-diff`: Print a diff report when changes are detected
- `--timeout`: SSH connection timeout in seconds (default: 30)

#### Policy Options
- `--separate, -s`: One file per AS
- `--output-dir`: Policy output directory
- `--test`: Test bgpq4 connectivity
- `--test-as`: AS number to use for connectivity test (default 7922)
- `--timeout`: bgpq4 command timeout (seconds)

#### Apply Options
- `--router HOSTNAME`: Target router hostname (required)
- `--policy-dir DIR`: Base policy directory (expects `routers/<hostname>/` under it)
- `--dry-run`: Preview diff only
- `--confirm`: Use confirmed commit (auto‑rollback unless confirmed)
- `--confirm-timeout N`: Confirmation timeout (seconds)
- `--diff-format {text,set,xml}`: Diff format
- `--skip-safety`: Skip safety validation (not recommended)
- `--force`: Force despite high risk (not recommended)
- `--yes, -y`: Skip interactive prompt
- `--username/--password/--ssh-key/--port/--timeout/--comment`: NETCONF connection and commit options

## Configuration

### Environment Variables

```bash
# SSH defaults used by collectors
export SSH_USERNAME=admin
export SSH_PASSWORD=secret
export SSH_KEY_PATH=/path/to/key

# NETCONF (apply) credentials
export NETCONF_USERNAME=admin
export NETCONF_PASSWORD=secret
export NETCONF_SSH_KEY=/path/to/key

# IRR proxy
export OTTO_BGP_PROXY_ENABLED=true
export OTTO_BGP_PROXY_JUMP_HOST=gateway.example.com
export OTTO_BGP_PROXY_JUMP_USER=admin
export OTTO_BGP_PROXY_SSH_KEY=/path/to/key
export OTTO_BGP_PROXY_KNOWN_HOSTS=/path/to/known_hosts

# RPKI cache directory (for validator)
export OTTO_BGP_RPKI_CACHE_DIR=/var/lib/otto-bgp/rpki

# Output base directory for pipeline
export OTTO_BGP_OUTPUT_DIR=/var/lib/otto-bgp
```

### Configuration File

Config is loaded from these locations (first found): `~/.bgp-toolkit.json`, `/etc/otto-bgp/config.json`, `./bgp-toolkit.json`.

Minimal example `/etc/otto-bgp/config.json` matching v0.3.2:

```json
{
  "ssh": {
    "username": "admin",
    "connection_timeout": 30,
    "command_timeout": 60
  },
  "output": {
    "default_output_dir": "/var/lib/otto-bgp"
  },
  "installation_mode": {
    "type": "system",
    "service_user": "otto-bgp"
  },
  "autonomous_mode": {
    "enabled": false,
    "auto_apply_threshold": 100,
    "require_confirmation": true,
    "notifications": {
      "email": {
        "enabled": true,
        "smtp_server": "smtp.company.com",
        "smtp_port": 587,
        "smtp_use_tls": true,
        "from_address": "otto-bgp@company.com",
        "to_addresses": ["network-team@company.com"],
        "subject_prefix": "[Otto BGP Autonomous]"
      }
    }
  },
  "rpki": {
    "enabled": true,
    "fail_closed": true,
    "max_vrp_age_hours": 24,
    "vrp_cache_path": "/var/lib/otto-bgp/rpki/vrp_cache.json",
    "allowlist_path": "/var/lib/otto-bgp/rpki/allowlist.json"
  },
  "irr_proxy": {
    "enabled": false,
    "method": "ssh_tunnel",
    "jump_host": "",
    "jump_user": "",
    "tunnels": [
      { "name": "ntt", "local_port": 43001, "remote_host": "rr.ntt.net", "remote_port": 43 },
      { "name": "radb", "local_port": 43002, "remote_host": "whois.radb.net", "remote_port": 43 }
    ]
  }
}
```

## Production Workflow

This section shows the **actual workflow** used by production deployments today. Otto BGP provides policy generation automation while maintaining safety through manual review and application processes.

### Typical Production Deployment

**Step 1: Automated Policy Generation**
```bash
# Option A: systemd (recommended)
sudo systemctl enable otto-bgp.timer && sudo systemctl start otto-bgp.timer

# Option B: manual pipeline execution
./otto-bgp pipeline devices.csv --output-dir ./policies/$(date +%Y%m%d)
```

**Step 2: Policy Review and Validation**
```bash
# Review generated policies
ls -la ./policies/$(date +%Y%m%d)/routers/
diff -ru ./policies/previous/ ./policies/$(date +%Y%m%d)/ | head -40
```

**Step 3: Lab Testing (Optional but Recommended)**
```bash
# Test policies in lab environment using NETCONF
./otto-bgp apply --router lab-router1 --policy-dir ./policies/$(date +%Y%m%d)/ --dry-run
./otto-bgp apply --router lab-router1 --policy-dir ./policies/$(date +%Y%m%d)/ --confirm
```

**Step 4: Change Management Integration**
```bash
# Create change request in your CM system
# Include generated policies and lab test results
# Attach change-summary.txt and any test outputs
# Schedule application during maintenance window
```

**Step 5: Manual Policy Application**
```bash
# During maintenance window, apply policies manually:
# 1. Load generated policies to router configuration candidate
# 2. Review configuration diff
# 3. Commit with confirmation timeout
# 4. Monitor BGP sessions and routing tables
# 5. Confirm commit on the device (no `apply-confirm` subcommand in v0.3.2)
```

## Enhanced Policy Automation

### Production-Ready Policy Application

**Otto BGP v0.3.2 provides multiple policy application approaches:**

**Autonomous Mode:**
- Risk-based decisions (auto‑apply only low risk)
- Email notifications on NETCONF events (if configured)
- Always‑on guardrails and safety validation
- Manual fallback for higher‑risk changes

**Manual Mode (Traditional):**
- Generate policies with Otto BGP: `./otto-bgp policy as-numbers.txt -o policies.txt`
- Review generated policies manually or with automation tools
- Test in development environment first
- Apply using existing change management procedures

### Automated Policy Application

**Prerequisites for Autonomous Operation:**
```bash
# Install PyEZ dependencies
pip install junos-eznc jxmlease lxml ncclient

# Configure Otto BGP for autonomous mode
./install.sh --autonomous
```

**Autonomous Mode Commands:**
```bash
# Unified autonomous pipeline
./otto-bgp pipeline devices.csv --autonomous --mode autonomous

# Manual confirmation example (non‑autonomous)
./otto-bgp apply --router router1 --confirm --confirm-timeout 120
```

### IRR Proxy Support

See IRR Proxy Workflow above. `policy` and `pipeline` automatically use the proxy when enabled in configuration.

### Complete Automation Workflow
```bash
# 1. Generate router-specific policies
./otto-bgp pipeline devices.csv --output-dir policies

# 2. Monitor autonomous operations via email notifications and logs
sudo journalctl -u otto-bgp-autonomous.service -f

# Re-run as needed
./otto-bgp pipeline devices.csv --output-dir policies
```

## Minimal Lab Setup

For testing against real lab routers with production-like configuration:

- ✅ **Lab System**: Install prerequisites on dedicated lab server (Python 3.9+, bgpq4, SSH client)
- ✅ **Otto Deployment**: Clone and configure using installation and user setup steps
- ✅ **Lab SSH Keys**: Generate production-style keypair via SSH key configuration
- ✅ **Router Config**: Deploy SSH user and keys on lab routers using Juniper SSH user setup
- ✅ **Device Inventory**: Create `devices.csv` with lab router IPs following device inventory setup
- ✅ **Security Setup**: Collect lab router host keys via SSH host key verification
- ✅ **Production Config**: Mirror production settings with configuration setup 
- ✅ **Lab Pipeline**: Test full workflow with real BGP data using pipeline command

**Lab Validation**: `./otto-bgp pipeline lab-devices.csv --output-dir ./lab-results` against live routers.

## Monitoring

### SystemD Integration
```bash
# Service status
sudo systemctl status otto-bgp.service

# Recent executions
sudo systemctl list-timers otto-bgp.timer

# Service logs
sudo journalctl -u otto-bgp.service --since "1 hour ago"

# Follow live logs
sudo journalctl -u otto-bgp.service -f
```

### Log Analysis
```bash
# View execution summary
sudo grep "Pipeline execution complete" /var/lib/otto-bgp/logs/otto-bgp.log | tail -5

# Check for errors
sudo grep "ERROR" /var/lib/otto-bgp/logs/otto-bgp.log | tail -10

# Monitor performance
sudo grep "took.*s" /var/lib/otto-bgp/logs/otto-bgp.log | tail -10
```

### Health Monitoring Script
```bash
# Create monitoring script
sudo tee /usr/local/bin/otto-bgp-health << 'EOF'
#!/bin/bash
# Otto BGP Health Check

LOG_FILE="/var/lib/otto-bgp/logs/otto-bgp.log"
LAST_RUN=$(sudo systemctl show otto-bgp.service -p ActiveEnterTimestamp --value)
OUTPUT_DIR="/var/lib/otto-bgp/output"

echo "Otto BGP Health Status"
echo "========================="
echo "Last execution: $LAST_RUN"
echo "Service status: $(sudo systemctl is-active otto-bgp.service)"
echo "Timer status: $(sudo systemctl is-active otto-bgp.timer)"
echo "Output files: $(find $OUTPUT_DIR -name "*.txt" -mtime -1 | wc -l) (last 24h)"

# Recent errors
ERROR_COUNT=$(sudo grep -c "ERROR" $LOG_FILE)
if [ $ERROR_COUNT -gt 0 ]; then
    echo "Recent errors: $ERROR_COUNT"
    echo "Latest error:"
    sudo grep "ERROR" $LOG_FILE | tail -1
fi
EOF

sudo chmod +x /usr/local/bin/otto-bgp-health
```

### Alerting Integration
```bash
# Example: Send email alerts on failures
sudo tee /etc/systemd/system/otto-bgp-failure@.service << 'EOF'
[Unit]
Description=Otto BGP Failure Notification
After=otto-bgp.service

[Service]
Type=oneshot
ExecStart=/usr/bin/mail -s "Otto BGP Failed on %H" admin@company.com < /var/log/otto-bgp-error.log
EOF

# Add to main service
# OnFailure=otto-bgp-failure@%i.service
```

## Integration

### Systemd Integration

Enable automated policy updates:

```bash
# Install service files
sudo cp systemd/otto-bgp.service /etc/systemd/system/
sudo cp systemd/otto-bgp.timer /etc/systemd/system/

# Enable and start
sudo systemctl enable otto-bgp.timer
sudo systemctl start otto-bgp.timer

# Check status
sudo systemctl status otto-bgp.service
```

### Cron Integration

```cron
# Update BGP policies daily at 2 AM
0 2 * * * /opt/otto-bgp/venv/bin/python /opt/otto-bgp/otto_bgp/main.py pipeline /etc/otto-bgp/devices.csv --output-dir /var/lib/otto-bgp/policies
```

### CI/CD Integration

#### GitLab CI Example
```yaml
stages:
  - generate
  - validate

generate-policies:
  stage: generate
  script:
    - ./otto-bgp pipeline devices.csv --output-dir policies
  artifacts:
    paths:
      - policies/

validate-policies:
  stage: validate
  dependencies:
    - generate-policies
  script:
    - ./otto-bgp apply --router lab-router --dry-run --policy-dir policies/
```

#### Jenkins Pipeline
```groovy
pipeline {
    agent any

    stages {
        stage('Generate') {
            steps {
                sh './otto-bgp pipeline devices.csv --output-dir policies'
            }
        }

        stage('Validate') {
            steps {
                sh './otto-bgp apply --router ${ROUTER} --dry-run --policy-dir policies/'
            }
        }

        stage('Deploy') {
            when {
                branch 'main'
            }
            steps {
                sh './otto-bgp apply --router ${ROUTER} --confirm --policy-dir policies/'
            }
        }
    }
}
```

### Python Integration

```python
#!/usr/bin/env python3
"""
Example: Automated BGP policy management
"""

from otto_bgp.collectors import JuniperSSHCollector
from otto_bgp.discovery import RouterInspector, YAMLGenerator
from otto_bgp.generators import BGPq4Wrapper
from otto_bgp.appliers import JuniperPolicyApplier
from pathlib import Path

def automated_bgp_update(devices_csv: str, output_dir: str):
    """Complete automated BGP policy update"""
    
    # Initialize components
    collector = JuniperSSHCollector()
    inspector = RouterInspector()
    yaml_gen = YAMLGenerator(output_dir=Path(output_dir))
    bgpq4 = BGPq4Wrapper()
    applier = JuniperPolicyApplier()
    
    # Phase 1: Discovery
    print("Phase 1: Discovering routers...")
    devices = collector.load_devices_from_csv(devices_csv)
    profiles = []
    
    for device in devices:
        try:
            bgp_config = collector.collect_bgp_config(device.address)
            profile = device.to_router_profile()
            profile.bgp_config = bgp_config
            profiles.append(profile)
        except Exception as e:
            print(f"Failed to discover {device.hostname}: {e}")
    
    # Phase 2: Generate mappings
    print("Phase 2: Generating mappings...")
    mappings = yaml_gen.generate_mappings(profiles)
    yaml_gen.save_with_history(mappings)
    
    # Phase 3: Generate policies
    print("Phase 3: Generating policies...")
    for hostname, data in mappings['routers'].items():
        as_numbers = data['discovered_as_numbers']
        if as_numbers:
            results = bgpq4.generate_policies_batch(as_numbers)
            bgpq4.write_policies_to_files(
                results,
                output_dir=f"{output_dir}/routers/{hostname}",
                separate_files=True
            )
    
    # Phase 4: Apply policies (with safety checks)
    print("Phase 4: Applying policies...")
    for hostname in mappings['routers'].keys():
        policy_dir = Path(f"{output_dir}/routers/{hostname}")
        if policy_dir.exists():
            policies = applier.load_router_policies(policy_dir)
            
            # Preview changes
            diff = applier.preview_changes(policies)
            print(f"Changes for {hostname}:\n{diff}")
            
            # Apply with confirmation
            result = applier.apply_with_confirmation(
                policies=policies,
                confirm_timeout=120,
                comment=f"Automated update for {hostname}"
            )
            
            if result.success:
                print(f"Successfully updated {hostname}")
            else:
                print(f"Failed to update {hostname}: {result.error_message}")

if __name__ == "__main__":
    automated_bgp_update("devices.csv", "policies")
```

## Best Practices

### 1. Safety First
- Always run dry-run before applying changes
- Use confirmed commits with appropriate timeouts
- Implement gradual rollout (lab → staging → production)
- Maintain rollback procedures

### 2. Discovery Practices
- Run discovery regularly to detect changes
- Review diff reports before policy updates
- Maintain historical mappings for audit
- Validate discovered AS numbers

### 3. Generation Practices
- Separate policies by router
- Cache generated policies
- Validate policy syntax
- Test with known AS numbers

### 4. Application Practices
- Apply during maintenance windows
- Monitor BGP sessions during updates
- Use confirmation timeouts
- Document all changes

### 5. Monitoring
- Track discovery changes over time
- Monitor policy generation failures
- Alert on application errors
- Maintain audit logs

## Troubleshooting

### Common Issues

#### 1. Discovery Failures
```bash
# Check SSH connectivity to devices
ssh admin@router1 "show version"

# Use the router-aware pipeline (the discover subcommand is disabled in v0.3.2)
./otto-bgp pipeline devices.csv -v --output-dir ./policies/test

# Test with a single device in the CSV
echo "hostname,address\nrouter1,10.1.1.1" > single.csv
./otto-bgp pipeline single.csv -v --output-dir ./policies/test
```

#### 2. Policy Generation Failures
```bash
# Test bgpq4 directly
bgpq4 -Jl test AS13335

# Check with container
docker run --rm ghcr.io/bgp/bgpq4:latest bgpq4 -Jl test AS13335

# Test through Otto
./otto-bgp policy test_as.txt --test --verbose
```

#### 3. Application Failures
```bash
# Check NETCONF connectivity
ssh admin@router1 -p 830 -s netconf

# Verify PyEZ installation
python3 -c "from jnpr.junos import Device; print('PyEZ OK')"

# Test with dry-run
./otto-bgp apply --router router1 --dry-run --verbose
```

#### 4. Proxy Issues
```bash
# Test SSH tunnel manually
ssh -L 43001:rr.ntt.net:43 admin@gateway.example.com

# Verify proxy configuration
./otto-bgp test-proxy --verbose

# Test bgpq4 through proxy
./otto-bgp test-proxy --test-bgpq4 --verbose
```

### Debug Mode

Enable comprehensive debugging:

```bash
# Verbose runtime logging
./otto-bgp pipeline devices.csv -v --output-dir ./policies/test

# Increase log level via env var
export OTTO_BGP_LOG_LEVEL=DEBUG
./otto-bgp policy as_list.txt -v

# Check systemd journal (system installs)
sudo journalctl -u otto-bgp.service --since "1 hour ago" -n 200
```

### Log Locations

- Service logs: `journalctl -u otto-bgp.service` (system mode) or `-u otto-bgp-autonomous.service`
- Per‑router metadata: `policies/routers/<hostname>/metadata.json`
- Reports: `policies/reports/`

## Advanced Topics

### Custom Workflows

Create custom automation workflows:

```python
from otto_bgp.pipeline import CustomPipeline

class MyBGPWorkflow(CustomPipeline):
    def pre_discovery_hook(self):
        """Custom pre-discovery logic"""
        pass
    
    def post_generation_hook(self, policies):
        """Custom post-generation validation"""
        pass
    
    def pre_application_hook(self, router, policies):
        """Custom pre-application checks"""
        pass
```

### Performance Tuning

```python
# Parallel discovery
wrapper = BGPq4Wrapper(
    max_workers=8,  # Parallel threads
    cache_ttl=3600,  # Cache for 1 hour
    batch_size=50    # Process in batches
)

# Connection pooling
collector = JuniperSSHCollector(
    pool_size=10,
    reuse_connections=True
)
```

### Integration APIs

Future REST API endpoints (planned):

```
GET  /api/v1/routers              # List routers
GET  /api/v1/routers/{id}         # Router details
POST /api/v1/discover             # Trigger discovery
POST /api/v1/generate             # Generate policies
POST /api/v1/apply                # Apply policies
GET  /api/v1/status               # System status
```
