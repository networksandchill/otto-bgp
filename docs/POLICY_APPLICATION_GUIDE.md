# Otto BGP Policy Application Guide

This guide explains how Otto BGP applies BGP policies to Juniper routers using NETCONF and provides workflows for development testing, autonomous operation, and traditional production deployment.

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Environment Setup](#environment-setup)
4. [Autonomous Operation](#autonomous-operation)
5. [Production Workflow](#production-workflow)
6. [Security Considerations](#security-considerations)
7. [Troubleshooting](#troubleshooting)
8. [Known Gaps and Limitations](#known-gaps-and-limitations)

## Overview

Otto BGP v0.3.2 generates BGP prefix-list policies using bgpq4 and provides NETCONF-based application to Juniper routers. The system includes comprehensive safety mechanisms including always-active guardrails, autonomous operation modes, email notifications, and risk-based decision making.

### Policy Operation Modes

- **Generation Only**: Creates Juniper policy-options configuration files for manual application
- **Autonomous Mode**: Unattended automatic policy application with always-active guardrails, risk-based decisions, and email audit trail
- **System Mode**: Interactive policy application with confirmation windows and safety checks

## Architecture

### Components

```
Otto BGP v0.3.2 NETCONF Application Stack
├── bgpq4 (IRR Query Engine)
│   └── Generates prefix-lists from AS numbers
├── Policy Adapter (otto_bgp/appliers/adapter.py)
│   └── Transforms policies for router contexts and BGP groups
├── NETCONF Applier (otto_bgp/appliers/juniper_netconf.py)
│   ├── PyEZ-based policy application via NETCONF
│   ├── Configuration preview and diff generation
│   ├── Confirmed commit with automatic rollback
│   └── Connection management with proper cleanup
├── Unified Safety Manager (otto_bgp/appliers/safety.py)
│   ├── Always-active guardrail system (cannot be disabled)
│   ├── Signal handling for graceful shutdown
│   ├── Thread-safe rollback callback management
│   ├── Risk-based autonomous decision logic
│   └── Email notifications for all NETCONF events
├── Guardrail Components (otto_bgp/appliers/guardrails.py)
│   ├── Prefix count validation
│   ├── Bogon prefix detection
│   ├── Concurrent operation prevention
│   ├── Signal handling for emergency stops
│   └── Optional RPKI validation integration
├── Exit Code System (otto_bgp/appliers/exit_codes.py)
│   └── Structured exit codes (300+ codes) for automation
└── Mode Manager (otto_bgp/appliers/mode_manager.py)
    └── System vs autonomous mode management with safety thresholds
```

### NETCONF Application Data Flow

1. **AS Discovery**: Extract AS numbers from router configurations or input files
2. **Policy Generation**: Query IRR databases via bgpq4 to generate prefix-lists
3. **Policy Adaptation**: Transform policies for specific routers and BGP groups
4. **Safety Assessment**: Always-active guardrails evaluate risk level
5. **NETCONF Connection**: Establish secure connection with SSH host key verification
6. **Configuration Preview**: Generate diff without applying changes (dry-run mode)
7. **Confirmed Commit**: Apply changes with automatic rollback window
8. **Health Validation**: Post-commit verification of router health
9. **Notification**: Email notifications for all NETCONF events (if enabled)
10. **Cleanup**: Proper connection cleanup and resource management

### RPKI Validation (Optional)

When enabled via configuration, Otto validates generated policies using a local VRP (Validated ROA Payloads) cache:

- **Cache Sources**: Supports routinator/rpki-client JSON format and CSV format
- **Validation Logic**: Tri-state validation (VALID/INVALID/NOT_FOUND) with configurable thresholds
- **Fail-Closed Mode**: Configurable behavior for stale or missing RPKI data
- **Guardrail Integration**: RPKI validation integrated as an optional guardrail component
- **Risk Assessment**: RPKI results contribute to overall risk level calculation

**Note**: RPKI validation requires external RPKI cache setup and is not included in the base installation.

## Discovery & Router Mapping

Otto can discover router BGP configuration via SSH and build router-aware mappings and inventories.

- Discover and persist mappings (YAML + history):
  - `otto-bgp discover --devices-csv devices.csv --output-dir policies`
  - Mappings saved under `policies/discovered/` with history and diff support
- List discovered data:
  - `otto-bgp list routers --output-dir policies`
  - `otto-bgp list as --output-dir policies`
  - `otto-bgp list groups --output-dir policies`
- Unified pipeline (collect → generate):
  - `otto-bgp pipeline devices.csv --output-dir policies`

## Environment Setup

### Prerequisites

#### 1. Install PyEZ Dependencies

```bash
# In your Otto BGP virtual environment
pip install junos-eznc jxmlease lxml ncclient
```

#### 2. Configure Lab Router

```junos
# Enable NETCONF
set system services netconf ssh

# Create configuration user
set system login class bgp-policy-admin permissions [configure view view-configuration]
set system login class bgp-policy-admin allow-commands "(show|commit|load|rollback|commit confirmed)"
set system login class bgp-policy-admin allow-configuration "policy-options prefix-list"
set system login class bgp-policy-admin allow-configuration "protocols bgp group .* import"

set system login user otto-lab class bgp-policy-admin
set system login user otto-lab authentication ssh-ed25519 "ssh-ed25519 AAAAC3Nz..."

commit comment "Otto BGP lab user setup"
```

#### 3. Configure NETCONF Credentials

Set credentials via environment variables or CLI flags:

```bash
# Environment variables (preferred for non-interactive use)
export NETCONF_USERNAME="otto-lab"
export NETCONF_PASSWORD="s3cr3t"           # or use NETCONF_SSH_KEY=/path/to/private_key
export NETCONF_PORT=830
export NETCONF_TIMEOUT=30

# Or pass as flags on apply:
otto-bgp apply --router lab-router1 --username otto-lab --ssh-key /var/lib/otto-bgp/ssh-keys/lab-key --dry-run
```

### Lab Testing Workflow

#### Step 1: Generate Policies

```bash
# Generate policies from ASN list
otto-bgp policy as_numbers.txt --output-dir lab_policies --separate

# Router-aware layout (used by apply):
# lab_policies/routers/<hostname>/AS<asn>_policy.txt
```

#### Step 2: Preview Changes

```bash
# Dry run to see what would change
otto-bgp apply --router lab-router1 --policy-dir lab_policies --dry-run

# Save diff for review
otto-bgp apply --router lab-router1 --policy-dir lab_policies --dry-run > changes.diff
```

#### Step 3: Apply with Confirmation

**Important**: The current implementation requires manual confirmation via the router's CLI within the timeout window.

```bash
# Apply with 2-minute confirmation window
otto-bgp apply --router lab-router1 --policy-dir lab_policies --confirm --confirm-timeout 120

# During the timeout window, connect to router and confirm:
ssh otto-lab@lab-router1
configure
commit

# If no manual confirmation within timeout, changes are automatically rolled back
```

#### Step 4: Verify Application

```bash
# Check applied policies
ssh otto-lab@lab-router1 "show configuration policy-options | match AS"

# Verify BGP import policies
ssh otto-lab@lab-router1 "show configuration protocols bgp | match import"

# Check BGP neighbor status
ssh otto-lab@lab-router1 "show bgp neighbor | match State"
```

## Autonomous Operation

### Overview

Otto BGP v0.3.2 provides autonomous operation that automatically applies low-risk BGP policy changes while maintaining always-active safety guardrails and comprehensive audit trails. Autonomous mode is controlled by the `OTTO_BGP_MODE=autonomous` environment variable and requires proper configuration for unattended operation.

### Autonomous Mode Setup

#### 1. Install with Autonomous Mode

```bash
# Install Otto BGP with autonomous mode configuration
./install.sh --autonomous

# This will:
# - Set up system-wide installation
# - Configure email notifications for NETCONF events
# - Require safety confirmation during setup
# - Enable risk-based autonomous decision logic
```

#### 2. Configure Email Notifications

During installation, you'll configure email settings for complete NETCONF event auditing:

```bash
SMTP server [smtp.company.com]: smtp.company.com
SMTP port [587]: 587
Use TLS encryption? [y/N]: y
From email address [otto-bgp@company.com]: otto-bgp@company.com
Engineer email address(es) (comma-separated): network-team@company.com,ops@company.com
```

Note: If storing SMTP secrets in files, ensure your service environment exports `OTTO_BGP_SMTP_PASSWORD` (the code reads the password from this env var). Systemd units can use an EnvironmentFile to populate it.

#### 3. Verify Configuration

```bash
# Check autonomous mode configuration
cat /etc/otto-bgp/config.json | jq '.autonomous_mode'

# Verify email notification settings
cat /etc/otto-bgp/config.json | jq '.autonomous_mode.notifications.email'

# Test email connectivity by checking logs
sudo journalctl -u otto-bgp.service | grep -i email
```

### Autonomous Operation Workflow

#### Risk-Based Decision Logic

Otto BGP autonomous mode only applies changes that meet strict safety criteria:

- **Risk Level Assessment**: Only `low` risk changes are auto-applied based on guardrail evaluation
- **Always-Active Guardrails**: All enabled guardrails must pass (cannot be disabled in production)
- **Safety Thresholds**: Configurable thresholds for prefix counts, RPKI validation rates, etc.
- **Confirmed Commits**: Uses confirmed commit with automatic rollback if health checks fail
- **Email Notifications**: Sent for all NETCONF events when both autonomous mode and email notifications are enabled

#### Autonomous Mode Operation

Autonomous mode is controlled by environment variables and configuration, not CLI flags:

```bash
# Set autonomous mode via environment variable
export OTTO_BGP_MODE=autonomous

# Run pipeline in autonomous mode
otto-bgp pipeline devices.csv --output-dir /var/lib/otto-bgp/output

# Apply policies in autonomous mode (mode detected automatically)
otto-bgp apply --router router1 --policy-dir /var/lib/otto-bgp/output

# Preview what autonomous mode would do (still requires explicit --dry-run)
otto-bgp apply --router router1 --policy-dir policies --dry-run
```

**Note**: The CLI does not include `--autonomous` or `--system` flags. Mode is detected from the `OTTO_BGP_MODE` environment variable or configuration files.

#### Safety Thresholds and Configuration

The `auto_apply_threshold` is **informational only** and appears in email notifications for context. It does not block operations:

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
        "send_on_success": true,
        "send_on_failure": true
      }
    }
  }
}
```

### Email Notification Examples

#### Successful Policy Application

```
Subject: [Otto BGP Autonomous] COMMIT - SUCCESS

NETCONF Event Notification
==========================
Event Type: COMMIT
Status: SUCCESS
Router: router1.company.com
Timestamp: 2025-08-17T14:30:15

Commit ID: 20250817-143015-001
Policies Applied: 3
AS Numbers: AS13335, AS15169, AS7922
Prefix Count: 150 (Reference threshold: 100)

Configuration Diff:
[+] policy-options {
[+]     replace: prefix-list AS13335 {
[+]         1.1.1.0/24;
[+]         1.0.0.0/24;
[+]     }
[+] }
```

#### Failed Policy Application

```
Subject: [Otto BGP Autonomous] COMMIT - FAILED

NETCONF Event Notification
==========================
Event Type: COMMIT
Status: FAILED
Router: router1.company.com
Timestamp: 2025-08-17T14:35:22

Error: Commit failed - configuration validation error
Attempted Policies: 1
Rollback Status: Automatic rollback attempted
```

### Monitoring Autonomous Operations

```bash
# Monitor systemd service logs for autonomous operations
sudo journalctl -u otto-bgp.service -f | grep -i "autonomous\|netconf\|commit"

# Check autonomous decision logs
cat /var/lib/otto-bgp/logs/otto-bgp.log | grep -i "autonomous\|risk\|threshold"

# Review email notification history
# (Check your email system for complete audit trail)

# Monitor router health after autonomous changes using router-native commands
# (e.g., show bgp summary / neighbor state on the router)
```

## Production Workflow

### Production Application Options

Otto BGP v0.3.2 provides two production-ready approaches for policy application:

1. **Autonomous Mode**: Automated application with risk-based decisions and email audit trail
2. **Traditional Manual**: Manual application through existing change management processes

### Traditional Manual Application Workflow

#### Step 1: Policy Generation

Use the provided systemd service and timer for scheduled runs.

```bash
# Enable and start the system timer for manual/system mode
sudo systemctl enable --now otto-bgp.timer

# Check timer status and next run time
systemctl list-timers | grep otto-bgp

# Policies will be saved under the configured output directory (e.g., /var/lib/otto-bgp/output/policies/)
```

#### Autonomous Scheduling (systemd)

For autonomous mode, use the autonomous service and timer.

```bash
# Enable and start the autonomous timer
sudo systemctl enable --now otto-bgp-autonomous.timer

# Check autonomous timer status and next run time
systemctl list-timers | grep otto-bgp-autonomous

# To adjust schedule, create a systemd drop-in override:
sudo systemctl edit otto-bgp-autonomous.timer
# Then set a different OnCalendar= value and reload
sudo systemctl daemon-reload
sudo systemctl restart otto-bgp-autonomous.timer
```

#### Step 2: Change Management Process

```python
#!/usr/bin/env python3
# Example change validation script

import difflib
import json
from pathlib import Path

def validate_policy_changes(old_policy, new_policy):
    """Validate policy changes before production application"""
    
    # Generate diff
    diff = difflib.unified_diff(
        old_policy.splitlines(),
        new_policy.splitlines(),
        lineterm=''
    )
    
    # Check diff size
    diff_lines = list(diff)
    if len(diff_lines) > 1000:
        raise ValueError("Policy change too large for automated approval")
    
    # Check for removals (risky)
    removals = [l for l in diff_lines if l.startswith('-')]
    if len(removals) > 100:
        raise ValueError("Too many prefix removals - manual review required")
    
    return {
        'additions': len([l for l in diff_lines if l.startswith('+')]),
        'removals': len(removals),
        'total_changes': len(diff_lines),
        'approved': True
    }

# Use in production workflow
old = Path('/var/lib/otto-bgp/policies/current/AS13335.txt').read_text()
new = Path('/var/lib/otto-bgp/policies/pending/AS13335.txt').read_text()
result = validate_policy_changes(old, new)
```

#### Step 3: Manual Application

```bash
# 1. Create change request
./create-change-request.sh "BGP Policy Update $(date +%Y%m%d)"

# 2. Load configuration in candidate
ssh netconf@router1
configure private
load merge /var/tmp/otto-bgp-policies.txt

# 3. Validate changes
show | compare
commit check

# 4. Apply during maintenance window
commit confirmed 5
# Monitor for 5 minutes
commit

# 5. Document change
./update-change-log.sh "BGP policies updated from Otto BGP"
```

## Security Considerations

### Authentication

#### SSH Keys (Recommended)

```bash
# Generate NETCONF-specific key
ssh-keygen -t ed25519 -f /var/lib/otto-bgp/ssh-keys/netconf-key -N ""

# Deploy to routers
ssh-copy-id -i /var/lib/otto-bgp/ssh-keys/netconf-key.pub otto-lab@lab-router1
```

#### Environment Variables (Development/Testing)

```bash
# Set credentials (avoid in production)
export NETCONF_USERNAME="otto-lab"
export NETCONF_SSH_KEY="/var/lib/otto-bgp/ssh-keys/netconf-key"

# Never use password in production
# export NETCONF_PASSWORD="password"  # DON'T DO THIS
```

### Access Control

#### Juniper Configuration Class

```junos
# Minimal required permissions for policy application
set system login class bgp-policy-admin permissions configure
set system login class bgp-policy-admin permissions view-configuration

# Restrict to policy-options only
set system login class bgp-policy-admin allow-configuration "policy-options prefix-list AS[0-9]+"
set system login class bgp-policy-admin deny-configuration "policy-options prefix-list (?!AS[0-9]+)"

# Restrict BGP changes to import policies only
set system login class bgp-policy-admin allow-configuration "protocols bgp group .* import"
set system login class bgp-policy-admin deny-configuration "protocols bgp group .* (?!import)"

# Deny system changes
set system login class bgp-policy-admin deny-configuration "system"
set system login class bgp-policy-admin deny-configuration "interfaces"
set system login class bgp-policy-admin deny-configuration "routing-options"
```

### Audit Logging

```junos
# Enable configuration change logging
set system syslog file config-changes change-log info
set system syslog file config-changes match "UI_COMMIT|UI_COMMIT_CONFIRMED|UI_ROLLBACK"

# Log NETCONF actions
set system syslog file netconf-log daemon info
set system syslog file netconf-log match NETCONF
```

## Troubleshooting

### Common Issues

#### 1. PyEZ Not Available

```bash
# Check if PyEZ is installed in your virtual environment
# For development:
source otto_venv/bin/activate
# Or use production paths:
# System: /usr/local/venv/bin/python
# User: ~/.local/venv/bin/python
python -c "import jnpr.junos; print('PyEZ available')"

# If not, install PyEZ and dependencies
pip install junos-eznc jxmlease lxml ncclient
```

#### 2. NETCONF Connection Failed

```bash
# Test NETCONF connectivity
ssh -p 830 otto-lab@lab-router1 -s netconf

# Check NETCONF is enabled
ssh otto-lab@lab-router1 "show configuration system services | match netconf"
```

#### 3. Permission Denied

```bash
# Verify user permissions
ssh otto-lab@lab-router1 "show cli authorization"

# Check specific permission
ssh otto-lab@lab-router1 "show configuration system login class bgp-policy-admin"
```

#### 4. Commit Failed

Common commit failures and solutions:

```bash
# Check router disk space
ssh otto-lab@lab-router1 "show system storage"

# Check for configuration errors
ssh otto-lab@lab-router1 "show system commit"

# Debug via Python (in development venv or production)
python3 -c "
from jnpr.junos import Device
from jnpr.junos.utils.config import Config

dev = Device(host='lab-router1', user='otto-lab')
dev.open()
config = Config(dev)

# Load test policy
config.load('policy-options { prefix-list test { 192.168.1.0/24; } }', format='text', merge=True)

# Check configuration validity
result = config.commit_check()
print(f'Commit check: {result}')

# Show diff if valid
if result:
    print('Diff:')
    print(config.pdiff())

config.rollback()
dev.close()
"
```

### Logging and Debugging

#### Enable Debug Logging

```bash
# Enable debug logging via environment variable
export OTTO_BGP_LOG_LEVEL=DEBUG

# Run with verbose output
otto-bgp apply --router lab-router1 --dry-run --verbose

# Check Otto BGP logs
tail -f /var/lib/otto-bgp/logs/otto-bgp.log

# Enable PyEZ debug logging (for development)
export PYTHONPATH=/path/to/otto-bgp:$PYTHONPATH
python3 -c "
import logging
import os
logging.basicConfig(level=logging.DEBUG)

from jnpr.junos import Device
dev = Device(host='lab-router1', user='otto-lab', gather_facts=True)
dev.open()
print('Device Facts:')
for key, value in dev.facts.items():
    print(f'  {key}: {value}')
dev.close()
"
```

#### Monitor Application

```bash
# Watch Otto BGP logs
tail -f /var/lib/otto-bgp/logs/otto-bgp.log | grep -E "(NETCONF|apply|commit)"

# Monitor router logs
ssh otto-lab@router "monitor start messages"
# Run apply command
ssh otto-lab@router "monitor stop"
```

## Best Practices

### 1. Always Test in Lab First

```bash
# Lab testing checklist
- [ ] Generate policies for test AS numbers
- [ ] Preview changes with --dry-run
- [ ] Apply with short confirmation timeout
- [ ] Verify BGP sessions remain stable
- [ ] Check routing table for anomalies
- [ ] Document any issues found
```

### 2. Use Confirmation Windows

```bash
# Always use confirmed commits with adequate timeout
otto-bgp apply --router router1 --confirm --confirm-timeout 300

# Manually confirm via router CLI within timeout window
ssh admin@router1
configure
commit

# If no confirmation, automatic rollback occurs
# Manual rollback can be performed if needed:
ssh admin@router1 "configure; rollback 1; commit"
```

### 3. Monitor After Application

```bash
# Create monitoring script
#!/bin/bash
ROUTER=$1
CHECK_INTERVAL=30
CHECKS=10

for i in $(seq 1 $CHECKS); do
    echo "Check $i/$CHECKS at $(date)"
    ssh monitor@$ROUTER "show bgp summary | match Establ"
    sleep $CHECK_INTERVAL
done
```

### 4. Maintain Rollback Capability

```junos
# Configure rollback on router
set system max-configurations-on-flash 50
set system max-configuration-rollbacks 50

# Before major changes
request system configuration rescue save

# Quick rollback if needed
rollback 1
commit
```

## Integration Examples

### GitOps Workflow

```yaml
# .gitlab-ci.yml example
stages:
  - generate
  - validate
  - deploy

generate-policies:
  stage: generate
  script:
    - ./otto-bgp pipeline devices.csv --output-dir policies/
  artifacts:
    paths:
      - policies/

validate-policies:
  stage: validate
  script:
    - python validate_policies.py policies/
    - otto-bgp apply --router lab-router1 --dry-run
  
deploy-to-lab:
  stage: deploy
  when: manual
  script:
    - otto-bgp apply --router lab-router1 --confirm
  environment:
    name: lab
```

### Ansible Integration

```yaml
---
- name: Apply BGP Policies via Otto BGP
  hosts: juniper_routers
  gather_facts: no
  
  tasks:
    - name: Generate policies
      command: otto-bgp policy as_list.txt -o /tmp/policies/
      delegate_to: localhost
      
    - name: Load policies to router
      juniper_junos_config:
        load: merge
        src: "/tmp/policies/{{ inventory_hostname }}_policy.txt"
        confirmed: 5
        comment: "Otto BGP policy update"
        
    - name: Verify BGP sessions
      juniper_junos_command:
        commands:
          - show bgp summary
        wait_for:
          - result[0] contains Establ
          
    - name: Confirm changes
      juniper_junos_config:
        commit: yes
```

## Conclusion

Otto BGP v0.3.2 provides a complete pipeline for BGP policy management, from generation to NETCONF-based application. The always-active guardrail system, risk-based decision logic, and comprehensive audit trail enable both interactive and autonomous policy application.

### Deployment Recommendations

**For Autonomous Mode:**
1. Configure Otto BGP with appropriate configuration files and environment variables
2. Set up email notifications for complete audit trail of all NETCONF events
3. Monitor systemd logs and email notifications for operational visibility
4. Ensure SSH host key verification is properly configured
5. Test guardrail system and rollback procedures in lab environment

**For System Mode (Interactive):**
1. Generate policies using Otto BGP policy generation features
2. Use `--dry-run` to preview all changes before application
3. Apply with confirmed commits and adequate timeout windows
4. Monitor BGP session health during and after application
5. Maintain documented rollback procedures

**Prerequisites for All Modes:**
- PyEZ (junos-eznc) and dependencies installed in Otto BGP virtual environment
- NETCONF enabled on target Juniper routers with appropriate user permissions
- SSH host key verification configured with known_hosts file
- Guardrail system enabled (always active, cannot be disabled)

For additional support, refer to the main README.md or create an issue in the Otto BGP repository.

## Known Gaps and Limitations

### NETCONF Implementation Limitations

1. **Juniper Router Support Only**: NETCONF functionality is currently limited to Juniper routers. Other vendor support is not implemented.

2. **Limited Health Validation**: Post-commit health checks focus on management reachability and BGP session state. Deeper device health validation is still manual.

### Configuration and Setup Considerations

1. **Installation Script Scope**: `./install.sh --autonomous` provisions core services, but operators must still review configuration (SMTP, device inventory, guardrail thresholds) before production use.

2. **Email Notification Requirements**: The WebUI persists SMTP configuration (including recipients) into `config.json` and normalizes env overrides, but successful delivery still depends on external SMTP reachability and credentials management.

3. **RPKI Validation Prerequisites**: `otto-bgp-rpki-update.timer` refreshes VRP caches and the preflight service runs before autonomous jobs. Environments without outbound access must supply offline mirrors for the configured cache paths.

### Operational Limitations

1. **Limited Error Recovery**: While rollback capabilities exist, automated recovery beyond basic rollback is limited. Complex failure scenarios may require manual intervention.

2. **Multi-Router Coordinator Scope**: The `--multi-router` workflow orchestrates staged rollouts, but it assumes a healthy database backend and does not yet coordinate cross-device rollback logic beyond stage-level success/failure.

3. **Diff Analysis Depth**: Configuration diff reporting highlights added/removed AS mappings; deep semantic analysis of large policy changes remains a manual review task.

### Documentation Coverage

1. **Troubleshooting Coverage**: Troubleshooting guidance does not cover every network connectivity, authentication, or configuration edge case.

2. **Performance Characteristics**: Documentation still lacks detailed sizing guidance for large policy sets and high-frequency pipelines.
