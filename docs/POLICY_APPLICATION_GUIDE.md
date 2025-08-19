# Otto BGP Policy Application Guide

This guide explains how Otto BGP applies BGP policies to Juniper routers and provides workflows for development testing, autonomous operation, and traditional production deployment.

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Environment Setup](#environment-setup)
4. [Autonomous Operation](#autonomous-operation)
5. [Production Workflow](#production-workflow)
6. [Security Considerations](#security-considerations)
7. [Troubleshooting](#troubleshooting)

## Overview

Otto BGP v0.3.2 generates BGP prefix-list policies using bgpq4 and provides flexible application methods including autonomous operation with comprehensive safety controls, email notifications, and risk-based decision making.

### Policy Operation Modes

- **Generation Only**: Creates Juniper policy-options configuration files for manual application
- **Autonomous Mode**: Production-ready automatic policy application with risk-based decisions and email audit trail
- **Interactive Mode**: Manual policy application with confirmation windows and safety checks

## Architecture

### Components

```
Otto BGP v0.3.2 Enhanced Application Stack
├── bgpq4 (IRR Query Engine)
│   └── Generates prefix-lists from AS numbers
├── Policy Adapter (otto_bgp/appliers/adapter.py)
│   └── Transforms policies for router contexts
├── NETCONF Applier (otto_bgp/appliers/juniper_netconf.py)
│   └── PyEZ-based policy application with event notifications
├── Safety Validator (otto_bgp/appliers/safety.py)
│   ├── Risk-based autonomous decision logic
│   ├── Email notification system for all NETCONF events
│   └── Comprehensive pre-application validation
└── Configuration Manager (otto_bgp/utils/config.py)
    └── Autonomous mode configuration and email settings
```

### Enhanced Data Flow

1. **AS Discovery**: Extract AS numbers from router configurations
2. **Policy Generation**: Query IRR databases via bgpq4
3. **Policy Adaptation**: Transform for specific BGP groups
4. **Safety Assessment**: Risk-level evaluation and autonomous decision logic
5. **Application**: NETCONF commit with confirmation and event notifications
6. **Audit Trail**: Email notifications for all NETCONF operations (success/failure)
7. **Verification**: Post-application validation with monitoring recommendations

## Router Discovery

Otto BGP introduces automatic router discovery to understand your network topology and BGP relationships, enabling router-aware policy generation and application.

### Discovery Command
```bash
# Discover routers and their BGP configurations
./otto-bgp discover devices.csv --output-dir policies

# Show changes from previous discovery
./otto-bgp discover devices.csv --show-diff

# List discovered resources
./otto-bgp list routers
./otto-bgp list as
./otto-bgp list groups
```

### How Discovery Works
1. **Connect**: SSH to each router in devices.csv
2. **Inspect**: Parse BGP configuration to find groups and AS numbers
3. **Map**: Create AS-to-router and group relationships
4. **Store**: Save mappings in YAML for policy generation

### Discovery Output
```
policies/
├── discovered/
│   ├── router_mappings.yaml     # AS-to-router mappings
│   ├── router_inventory.yaml    # Router profiles
│   └── history/                 # Previous discoveries
└── routers/                     # Router-specific policies
```

### Integration with Policy Application

The discovery process creates router-aware mappings that enhance policy application:

- **AS-to-Router Mapping**: Knows which routers use specific AS numbers
- **BGP Group Context**: Understands router-specific BGP group structures
- **Change Detection**: Identifies topology changes between discovery runs
- **Router Profiles**: Maintains device metadata for targeted policy application

This discovery data enables Otto BGP to generate router-specific policies and apply them with full context awareness during autonomous operations.

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

#### 3. Configure Otto BGP

Create `/etc/otto-bgp/netconf.json`:
```json
{
  "lab_routers": {
    "lab-router1": {
      "hostname": "192.168.100.1",
      "username": "otto-lab",
      "ssh_key": "/var/lib/otto-bgp/ssh-keys/lab-key",
      "port": 830
    }
  },
  "safety": {
    "max_prefix_lists": 100,
    "max_prefixes_per_list": 10000,
    "require_confirmation": true,
    "confirm_timeout": 120
  }
}
```

### Lab Testing Workflow

#### Step 1: Generate Policies

```bash
# Extract AS numbers from router
./otto-bgp discover lab-devices.csv

# Generate policies
./otto-bgp policy collected_as.txt -o lab_policies/
```

#### Step 2: Preview Changes

```bash
# Dry run to see what would change
./otto-bgp apply --router lab-router1 --dry-run

# Review the diff
./otto-bgp apply --router lab-router1 --dry-run > changes.diff
```

#### Step 3: Apply with Confirmation

```bash
# Apply with 2-minute confirmation window
./otto-bgp apply --router lab-router1 --confirm --confirm-timeout 120

# Monitor BGP sessions
ssh otto-lab@lab-router1 "show bgp summary"

# If everything looks good, commit happens automatically after timeout
# If issues occur, let timeout expire for automatic rollback
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

Otto BGP v0.3.2 introduces production-ready autonomous operation that automatically applies low-risk BGP policy changes while maintaining comprehensive safety controls and audit trails.

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

- **Risk Level**: Only `low` risk changes are auto-applied
- **Safety Validation**: All existing safety checks must pass
- **Confirmation Timeout**: Confirmed commits with automatic rollback
- **Email Notifications**: Every NETCONF operation generates email notification

#### Example Autonomous Commands

```bash
# Standard autonomous operation
./otto-bgp apply --autonomous --auto-threshold 100

# System mode with autonomous decisions
./otto-bgp apply --system --autonomous

# Full pipeline with autonomous application
./otto-bgp pipeline devices.csv --autonomous --system

# Preview autonomous decisions (dry run)
./otto-bgp apply --autonomous --dry-run
```

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
[+]     prefix-list AS13335 {
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

Error: Configuration check failed: prefix-list AS13335 already exists
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

# Monitor router health after autonomous changes
./otto-bgp discover devices.csv --show-diff
```

## Production Workflow

### Production Application Options

Otto BGP v0.3.2 provides two production-ready approaches for policy application:

1. **Autonomous Mode**: Automated application with risk-based decisions and email audit trail
2. **Traditional Manual**: Manual application through existing change management processes

### Traditional Manual Application Workflow

#### Step 1: Policy Generation

```bash
# Run Otto BGP on schedule (e.g., daily via cron)
0 2 * * * /opt/otto-bgp/venv/bin/python /opt/otto-bgp/otto_bgp/main.py pipeline /var/lib/otto-bgp/devices.csv

# Policies saved to: /var/lib/otto-bgp/output/policies/
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
# Check if PyEZ is installed
python -c "import jnpr.junos; print('PyEZ available')"

# If not, install it
pip install junos-eznc
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

```python
# Debug commit issues
from jnpr.junos import Device
from jnpr.junos.utils.config import Config

dev = Device(host='lab-router1', user='otto-lab')
dev.open()
config = Config(dev)

# Load and check
config.load(path='policy.txt', merge=True)
config.pdiff()  # Show pending diff

# Check for errors
if config.commit_check():
    print("Configuration is valid")
else:
    print("Configuration has errors")
    
dev.close()
```

### Logging and Debugging

#### Enable Debug Logging

```python
# In otto_bgp/appliers/juniper_netconf.py
import logging
logging.basicConfig(level=logging.DEBUG)

# PyEZ debug
from jnpr.junos import Device
dev = Device(host='router', gather_facts=True, normalize=True)
dev.open()
print(dev.facts)  # Show device information
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
# Never skip confirmation in production-like environments
./otto-bgp apply --router router1 --confirm --confirm-timeout 300

# Have rollback plan ready (use router's native rollback)
ssh admin@router1 "rollback 1; commit"
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
    - ./otto-bgp apply --router lab-router1 --dry-run
  
deploy-to-lab:
  stage: deploy
  when: manual
  script:
    - ./otto-bgp apply --router lab-router1 --confirm
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
      command: ./otto-bgp policy as_list.txt -o /tmp/policies/
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

Otto BGP v0.3.2 provides a complete pipeline for BGP policy management, from generation to autonomous application. The enhanced safety controls, risk-based decision logic, and comprehensive email audit trail make automated policy application suitable for production environments.

### Deployment Recommendations

**For Autonomous Mode (Recommended for Production):**
1. Configure Otto BGP with `./install.sh --autonomous`
2. Set up email notifications for complete audit trail
3. Monitor systemd logs and email notifications
4. Maintain rollback capability on routers
5. Start with low auto_apply_threshold for context

**For Traditional Manual Mode:**
1. Generate policies with Otto BGP
2. Review and validate changes
3. Apply through your standard change process
4. Monitor BGP health after changes
5. Maintain rollback capability

For additional support, refer to the main README.md or create an issue in the Otto BGP repository.